from c2corg_api.scripts.migration.batch import Batch


class DocumentBatch(Batch):
    """A batch implementation for documents that have archive documents,
    locales and geometries.
    """

    def __init__(self, session, batch_size,
                 model_document, model_archive_document,
                 model_geometry, model_archive_geometry):
        super(DocumentBatch, self).__init__(session, batch_size)

        self.model_document = model_document
        self.model_archive_document = model_archive_document
        self.model_geometry = model_geometry
        self.model_archive_geometry = model_archive_geometry

        self.documents = []
        self.archive_documents = []
        self.geometries = []
        self.archive_geometries = []

    def add_document(self, document):
        self.documents.append(document)
        self.flush_or_not()

    def add_archive_documents(self, archive_documents):
        self.archive_documents.extend(archive_documents)

    def add_geometry(self, geometry):
        self.geometries.append(geometry)

    def add_geometry_archives(self, geometry_archives):
        self.archive_geometries.extend(geometry_archives)

    def should_flush(self):
        return len(self.documents) > self.batch_size

    def flush(self):
        if self.documents:
            self.session.bulk_insert_mappings(
                self.model_document, self.documents)
            self.session.flush()
            self.documents = []
        if self.archive_documents:
            self.session.bulk_insert_mappings(
                self.model_archive_document, self.archive_documents)
            self.session.flush()
            self.archive_documents = []
        if self.geometries:
            self.session.bulk_insert_mappings(
                self.model_geometry, self.geometries)
            self.session.flush()
            self.geometries = []
        if self.archive_geometries:
            self.session.bulk_insert_mappings(
                self.model_archive_geometry, self.archive_geometries)
            self.session.flush()
            self.archive_geometries = []
