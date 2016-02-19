from c2corg_api.models.image import Image, ArchiveImage, IMAGE_TYPE
from c2corg_api.models.document import DocumentLocale, ArchiveDocumentLocale, \
    DOCUMENT_TYPE
from c2corg_api.scripts.migration.documents.document import MigrateDocuments


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
            'select count(*) from app_images_archives;'
        )

    def get_query(self):
        return (
            'select '
            '   id, document_archive_id, is_latest_version, '
            '   is_protected, redirects_to, '
            '   ST_Force2D(ST_SetSRID(geom, 3857)) geom, elevation, '
            '   filename, date_time, camera_name, exposure_time, '
            '   focal_length, fnumber, iso_speed, categories, activities, '
            '   author, image_type, has_svg, width, height, file_size '
            'from app_images_archives '
            'order by id, document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) from app_images_i18n_archives;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   id, document_i18n_archive_id, is_latest_version, culture, '
            '   name, description '
            'from app_images_i18n_archives '
            'order by id, document_i18n_archive_id;'
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
            has_svg=document_in.has_svg,
            width=document_in.width,
            height=document_in.height,
            file_size=document_in.file_size
        )

    def get_document_locale(self, document_in, version):
        description, summary = self.extract_summary(document_in.description)
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
