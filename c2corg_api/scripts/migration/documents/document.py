from sqlalchemy.orm.base import class_mapper
from sqlalchemy.sql import text
import transaction
import zope
import abc
import re

from c2corg_api.models.document import DocumentGeometry, \
    ArchiveDocumentGeometry
from c2corg_api.scripts.migration.documents.batch_document import DocumentBatch
from c2corg_api.scripts.migration.migrate_base import MigrateBase
from c2corg_common.attributes import quality_types


DEFAULT_QUALITY = quality_types[2]


class MigrateDocuments(MigrateBase):

    def __init__(self, connection_source, session_target, batch_size):
        super(MigrateDocuments, self).__init__(
            connection_source, session_target, batch_size)

    @abc.abstractmethod
    def get_model_document(self, locales):
        pass

    @abc.abstractmethod
    def get_model_archive_document(self, locales):
        pass

    def get_model_geometry(self):
        return DocumentGeometry

    def get_model_archive_geometry(self):
        return ArchiveDocumentGeometry

    @abc.abstractmethod
    def get_query(self):
        pass

    @abc.abstractmethod
    def get_count_query(self):
        pass

    @abc.abstractmethod
    def get_document(self, document_in, version):
        pass

    def get_document_archive(self, document_in, version):
        doc = self.get_document(document_in, version)
        doc['id'] = document_in.document_archive_id
        return doc

    @abc.abstractmethod
    def get_document_geometry(self, document_in, version):
        pass

    def get_document_geometry_archive(self, document_in, version):
        doc = self.get_document_geometry(document_in, version)
        doc['id'] = document_in.document_archive_id
        return doc

    @abc.abstractmethod
    def get_document_locale(self, document_in, version):
        pass

    def get_document_locale_archive(self, document_in, version):
        return self.get_document_locale(document_in, version)

    @abc.abstractmethod
    def get_name(self):
        pass

    def migrate(self):
        self._migrate(locales=False)
        self._migrate(locales=True)

    def _migrate(self, locales=False):
        self.start('{0}{1}'.format(
            'locales of ' if locales else '',
            self.get_name()))

        query_count = self.get_count_query_locales() if locales else \
            self.get_count_query()
        total_count = self.connection_source.execute(
            text(query_count)).fetchone()[0]

        print('Total: {0} rows'.format(total_count))

        query = text(self.get_query_locales() if locales else self.get_query())

        model_document = self.get_model_document(locales)
        # make sure that the version is not managed by SQLAlchemy, the value
        # that is provided as version should be used
        document_mapper = class_mapper(model_document)
        document_mapper.version_id_prop = None
        document_mapper.version_id_col = None
        document_mapper.version_id_generator = None

        if not locales:
            document_mapper = class_mapper(DocumentGeometry)
            document_mapper.version_id_prop = None
            document_mapper.version_id_col = None
            document_mapper.version_id_generator = None

        batch = DocumentBatch(
            self.session_target, self.batch_size,
            model_document,
            self.get_model_archive_document(locales),
            self.get_model_geometry(),
            self.get_model_archive_geometry())
        with transaction.manager, batch:
            count = 0
            current_document_id = None
            current_locale = None
            version = 1
            archives = []
            geometry_archives = []

            for document_in in self.connection_source.execute(query):
                count += 1
                if current_document_id is None:
                    current_document_id = document_in.id
                    version = 1
                    if locales:
                        current_locale = document_in.culture
                else:
                    if current_document_id != document_in.id:
                        print('WARNING: no latest version for {0}'.format(
                                current_document_id))
                        archives = []
                        geometry_archives = []
                        version = 1
                        current_document_id = document_in.id
                        if locales:
                            current_locale = document_in.culture

                if locales:
                    document_archive = self.get_document_locale_archive(
                        document_in, version)
                else:
                    document_archive = self.get_document_archive(
                        document_in, version)
                    geometry_archive = self.get_document_geometry_archive(
                            document_in, version)
                    geometry_archives.append(geometry_archive)
                archives.append(document_archive)

                if document_in.is_latest_version:
                    if locales:
                        if current_locale != document_in.culture:
                            raise Exception(
                                'locale of the latest version does not match '
                                'locale of the first version {0}'.format(
                                    current_document_id))
                        document = self.get_document_locale(
                            document_in, version)
                    else:
                        document = self.get_document(
                            document_in, version)
                        geometry = self.get_document_geometry(
                                document_in, version)
                        batch.add_geometry(geometry)
                    batch.add_geometry_archives(geometry_archives)
                    batch.add_archive_documents(archives)
                    batch.add_document(document)

                    archives = []
                    geometry_archives = []
                    version = 1
                    current_document_id = None
                    current_locale = None
                else:
                    version += 1
                self.progress(count, total_count)

            # the transaction will not be commited automatically when doing
            # a bulk insertion. `mark_changed` forces a commit.
            zope.sqlalchemy.mark_changed(self.session_target)
        self.stop()

    def merge_text(self, a, b):
        if not a:
            return b
        elif not b:
            return a
        else:
            return a + '\n' + b

    summary_regex = re.compile(
        '(\[abs(tract)?\]){1}?([\s\S]*?)(\[/abs(tract)?\]){1}?')

    def extract_summary(self, text):
        if text is None:
            return None, None

        match = MigrateDocuments.summary_regex.search(text)

        if match:
            text = MigrateDocuments.summary_regex.sub('', text).strip()
            summary = match.group(3)
            return text, summary
        else:
            return text, None

    def convert_tags(self, text):
        if not text:
            return text

        text = self.convert_q_tags(text)
        text = self.convert_c_tags(text)
        text = self.convert_wikilinks(
            text, MigrateDocuments.wikilink_waypoints_regex, 'waypoints')
        text = self.convert_wikilinks(
            text, MigrateDocuments.wikilink_profiles_regex, 'profiles')
        return text

    q_tag_regex = re.compile('\[(/?)q\]')

    def convert_q_tags(self, text):
        return MigrateDocuments.q_tag_regex.sub(r'[\1quote]', text)

    c_tag_regex = re.compile('\[(/?)c\]')

    def convert_c_tags(self, text):
        return MigrateDocuments.c_tag_regex.sub(r'[\1code]', text)

    wikilink_waypoints_regex = re.compile(
        '\[\[(summits|huts|parkings|sites|products)([^|]*)\|([^\]]+)\]\]')

    wikilink_profiles_regex = re.compile(
        '\[\[(users)([^|]*)\|([^\]]+)\]\]')  # noqa

    def convert_wikilinks(self, text, regex, route):
        match = regex.search(text)
        if match:
            text = regex.sub(r'[[%s\2|\3]]' % route, text)
        return text
