from c2corg_api.models.image import Image, ArchiveImage, IMAGE_TYPE
from c2corg_api.models.document import DocumentLocale, ArchiveDocumentLocale, \
    DOCUMENT_TYPE
from c2corg_api.scripts.migration.documents.document import MigrateDocuments, \
    DEFAULT_QUALITY


class MigrateImages(MigrateDocuments):

    def get_name(self):
        return 'images'

    def get_model_document(self, locales):
        return DocumentLocale if locales else Image

    def get_model_archive_document(self, locales):
        return ArchiveDocumentLocale if locales else ArchiveImage

    def get_document_geometry(self, document_in, version):
        return dict(
            document_id=document_in.id,
            id=document_in.id,
            version=version,
            geom=document_in.geom
        )

    def get_count_query(self):
        return (
            'select count(*) '
            'from app_images_archives ia join images i on ia.id = i.id '
            'where i.redirects_to is null;'
        )

    def get_query(self):
        return (
            'select '
            '   ia.id, ia.document_archive_id, ia.is_latest_version, '
            '   ia.is_protected, ia.redirects_to, '
            '   ST_Force2D(ST_SetSRID(ia.geom, 3857)) geom, ia.elevation, '
            '   ia.filename, ia.date_time, ia.camera_name, ia.exposure_time, '
            '   ia.focal_length, ia.fnumber, ia.iso_speed, ia.categories, '
            '   ia.activities, ia.author, ia.image_type, '
            '   ia.width, ia.height, ia.file_size '
            'from app_images_archives ia join images i on ia.id = i.id '
            'where i.redirects_to is null '
            'order by ia.id, ia.document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) '
            'from app_images_i18n_archives ia join images i on ia.id = i.id '
            'where i.redirects_to is null;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   ia.id, ia.document_i18n_archive_id, ia.is_latest_version, '
            '   ia.culture, ia.name, ia.description '
            'from app_images_i18n_archives ia join images i on ia.id = i.id '
            'where i.redirects_to is null '
            'order by ia.id, ia.culture, ia.document_i18n_archive_id;'
        )

    def get_document(self, document_in, version):
        return dict(
            document_id=document_in.id,
            type=IMAGE_TYPE,
            version=version,
            protected=document_in.is_protected,
            redirects_to=document_in.redirects_to,
            elevation=document_in.elevation,
            filename=document_in.filename,
            date_time=document_in.date_time,
            camera_name=document_in.camera_name,
            exposure_time=document_in.exposure_time,
            focal_length=document_in.focal_length,
            fnumber=document_in.fnumber,
            iso_speed=document_in.iso_speed,
            categories=self.convert_types(
                document_in.categories, MigrateImages.image_categories),
            activities=self.convert_types(
                document_in.activities, MigrateImages.activities),
            author=document_in.author,
            image_type=self.convert_type(
                document_in.image_type, MigrateImages.image_types),
            width=document_in.width,
            height=document_in.height,
            file_size=document_in.file_size,
            quality=DEFAULT_QUALITY
        )

    def get_document_locale(self, document_in, version):
        description = self.convert_tags(document_in.description)
        description, summary = self.extract_summary(description)
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            type=DOCUMENT_TYPE,
            version=version,
            lang=document_in.culture,
            title=document_in.name,
            description=description,
            summary=summary
        )

    activities = {
        '1': 'skitouring',
        '2': 'snow_ice_mixed',
        '3': 'mountain_climbing',
        '4': 'rock_climbing',
        '5': 'ice_climbing',
        '6': 'hiking',
        '7': 'snowshoeing',
        '8': 'paragliding'
    }

    image_types = {
        '1': 'collaborative',
        '2': 'personal',
        '3': 'copyright',
    }

    image_categories = {
        '1': 'landscapes',
        '6': 'detail',
        '3': 'action',
        '7': 'track',
        '8': 'rise',
        '9': 'descent',
        '4': 'topo',
        '2': 'people',
        '10': 'fauna',
        '11': 'flora',
        '16': 'snow',
        '12': 'geology',
        '13': 'hut',
        '14': 'equipment',
        '15': 'book',
        '17': 'help',
        '5': 'misc'
    }
