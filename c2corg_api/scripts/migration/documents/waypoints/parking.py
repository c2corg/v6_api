from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.scripts.migration.documents.document import DEFAULT_QUALITY
from c2corg_api.scripts.migration.documents.waypoints.waypoint import \
    MigrateWaypoints


class MigrateParkings(MigrateWaypoints):

    def get_name(self):
        return 'parking'

    def get_count_query(self):
        return (
            'select count(*) '
            'from app_parkings_archives pa join parkings p on pa.id = p.id '
            'where p.redirects_to is null;'
        )

    def get_query(self):
        return (
            'select '
            '   pa.id, pa.document_archive_id, pa.is_latest_version, '
            '   pa.elevation, pa.is_protected, pa.redirects_to, '
            '   ST_Force2D(ST_SetSRID(pa.geom, 3857)) geom,'
            '   pa.public_transportation_rating, pa.snow_clearance_rating, '
            '   pa.lowest_elevation, pa.public_transportation_types '
            'from app_parkings_archives pa join parkings p on pa.id = p.id '
            'where p.redirects_to is null '
            'order by pa.id, pa.document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) '
            'from app_parkings_i18n_archives pa '
            '  join parkings p on pa.id = p.id '
            'where p.redirects_to is null;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   pa.id, pa.document_i18n_archive_id, pa.is_latest_version, '
            '   pa.name, pa.description, '
            '   pa.public_transportation_description, '
            '   pa.snow_clearance_comment, pa.accommodation, pa.culture '
            'from app_parkings_i18n_archives pa '
            '  join parkings p on pa.id = p.id '
            'where p.redirects_to is null '
            'order by pa.id, pa.culture, pa.document_i18n_archive_id;'
        )

    def get_document(self, document_in, version):
        return dict(
            document_id=document_in.id,
            type=WAYPOINT_TYPE,
            version=version,
            waypoint_type='access',
            protected=document_in.is_protected,
            redirects_to=document_in.redirects_to,
            elevation=document_in.elevation,
            elevation_min=document_in.lowest_elevation,
            public_transportation_rating=self.convert_type(
                document_in.public_transportation_rating,
                MigrateParkings.public_transportation_ratings),
            snow_clearance_rating=self.convert_type(
                document_in.snow_clearance_rating,
                MigrateParkings.snow_clearance_ratings),
            public_transportation_types=self.convert_types(
                document_in.public_transportation_types,
                MigrateParkings.public_transportation_types, [0]),
            quality=DEFAULT_QUALITY
        )

    def get_document_locale(self, document_in, version):
        description = self.convert_tags(document_in.description)
        description, summary = self.extract_summary(description)

        description = self._add_accommodation(
            description,
            self.convert_tags(document_in.accommodation),
            document_in.culture)

        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            type=WAYPOINT_TYPE,
            version=version,
            lang=document_in.culture,
            title=document_in.name,
            description=description,
            summary=summary,
            access=self.convert_tags(
                document_in.public_transportation_description),
            access_period=self.convert_tags(document_in.snow_clearance_comment)
        )

    def _add_accommodation(self, description, accommodation, lang):
        if accommodation:
            header = self._translate_accomodation(lang)
            accommodation = '## ' + header + '\n' + accommodation
        return self.merge_text(description, accommodation)

    def _translate_accomodation(self, lang):
        return MigrateParkings.accomodation_translations[lang]

    accomodation_translations = {
        'ca': 'Allotjament, restauració i patrimoni cultural proper',
        'de': 'In der Nähe liegende Ess-, Trink- und Übernachtungsmöglichkeiten, sowie Kulturgüter',  # noqa
        'en': 'Nearby accomodation, restaurants and cultural heritage',
        'es': 'Alojamiento y comida en las cercanías',
        'eu': 'Inguruetako lo eta jateko tokiak',
        'fr': 'Hébergement, restauration et patrimoine culturel à proximité',
        'it': 'Vitto, alloggio nelle vicinanze e patrimonio culturale'
    }

    public_transportation_ratings = {
        '1': 'good service',
        '2': 'poor service',
        '3': 'no service',
        '4': 'nearby service',
        '5': 'seasonal service'
    }

    snow_clearance_ratings = {
        '1': 'often',
        '2': 'sometimes',
        '3': 'naturally',
        '4': 'non_applicable'
    }

    public_transportation_types = {
        '1': 'train',
        '2': 'bus',
        '3': 'service_on_demand',
        '4': 'boat',
        '9': 'cable_car'
    }
