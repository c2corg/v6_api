from c2corg_api.models.report import Report, ArchiveReport, REPORT_TYPE, \
    ReportLocale, ArchiveReportLocale
from c2corg_api.scripts.migration.documents.document import MigrateDocuments, \
    DEFAULT_QUALITY
from c2corg_api.scripts.migration.documents.routes import MigrateRoutes


class MigrateReports(MigrateDocuments):

    def get_name(self):
        return 'reports'

    def get_model_document(self, locales):
        return ReportLocale if locales else Report

    def get_model_archive_document(self, locales):
        return ArchiveReportLocale if locales else ArchiveReport

    def get_document_geometry(self, document_in, version):
        return dict(
            document_id=document_in.id,
            id=document_in.id,
            version=version,
            geom=document_in.geom
        )

    def get_count_query(self):
        return (
            ' select count(*) '
            ' from app_xreports_archives aa join xreports t on aa.id = t.id '
            ' where t.redirects_to is null;'
        )

    def get_query(self):
        return (
            ' select '
            '   aa.id, aa.document_archive_id, aa.is_latest_version, '
            '   aa.is_protected, aa.redirects_to, '
            '   ST_Force2D(ST_SetSRID(aa.geom, 3857)) geom, '
            '   aa.elevation, '
            '   aa.date, aa.event_type, '
            '   aa.activities, aa.nb_participants, aa.nb_impacted, '
            '   aa.rescue, aa.avalanche_level, aa.avalanche_slope, '
            '   aa.severity, aa.autonomy, '
            '   aa.author_status, aa.activity_rate, aa.nb_outings, '
            '   aa.age, aa.gender, aa.previous_injuries, '
            '   aa.autonomy '
            ' from app_xreports_archives aa join xreports t on aa.id = t.id '
            ' where t.redirects_to is null '
            ' order by aa.id, aa.document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            ' select count(*) '
            ' from app_xreports_i18n_archives aa '
            '   join xreports t on aa.id = t.id '
            ' where t.redirects_to is null;'
        )

    def get_query_locales(self):
        return (
            ' select '
            '    aa.id, aa.document_i18n_archive_id, aa.is_latest_version, '
            '    aa.culture, aa.name, aa.description, '
            '    aa.place, aa.route_study, aa.conditions, aa.training, '
            '    aa.motivations, aa.group_management, aa.risk, '
            '    aa.time_management, aa.safety, aa.reduce_impact, '
            '    aa.increase_impact, aa.modifications, aa.other_comments '
            ' from app_xreports_i18n_archives aa '
            '   join xreports t on aa.id = t.id '
            ' where t.redirects_to is null '
            ' order by aa.id, aa.culture, aa.document_i18n_archive_id;'
        )

    def get_document(self, document_in, version):
        return dict(
            document_id=document_in.id,
            type=REPORT_TYPE,
            version=version,

            quality=DEFAULT_QUALITY,

            elevation=document_in.elevation,
            date=document_in.date,
            activities=self.convert_types(
                document_in.activities, MigrateRoutes.activities),
            nb_participants=document_in.nb_participants,
            nb_impacted=document_in.nb_impacted,
            severity=self.convert_type(
                document_in.severity, MigrateReports.severity),
            rescue=document_in.rescue,
            event_type=self.convert_types(
                document_in.event_type, MigrateReports.event_types),

            avalanche_level=self.convert_type(
                document_in.avalanche_level, MigrateReports.avalanche_level),
            avalanche_slope=self.convert_type(
                document_in.avalanche_slope, MigrateReports.avalanche_slope),

            # Profile
            author_status=self.convert_type(
                document_in.author_status, MigrateReports.author_status),
            activity_rate=self.convert_type(
                document_in.activity_rate, MigrateReports.activity_rate),
            nb_outings=self.convert_type(
                document_in.nb_outings, MigrateReports.nb_outings),
            autonomy=self.convert_type(
                document_in.autonomy, MigrateReports.autonomy),
            age=document_in.age,
            gender=self.convert_type(
                document_in.gender, MigrateReports.gender),
            previous_injuries=self.convert_type(
                document_in.previous_injuries,
                MigrateReports.previous_injuries)
        )

    def get_document_locale(self, document_in, version):
        description, summary = self.extract_summary(document_in.description)
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            type=REPORT_TYPE,
            version=version,
            lang=document_in.culture,
            title=document_in.name,
            description=description,
            summary=summary,

            place=document_in.place,
            route_study=document_in.route_study,
            conditions=document_in.conditions,
            training=document_in.training,
            motivations=document_in.motivations,
            group_management=document_in.group_management,
            risk=document_in.risk,
            time_management=document_in.time_management,
            safety=document_in.safety,
            reduce_impact=document_in.reduce_impact,
            increase_impact=document_in.increase_impact,
            modifications=document_in.modifications,
            other_comments=document_in.other_comments
        )

    event_types = {
        '0': None,
        '1': 'avalanche',
        '2': 'stone_fall',
        '3': 'falling_ice',
        '7': 'person_fall',
        '6': 'crevasse_fall',
        '8': 'roped_fall',
        '9': 'physical_failure',
        '4': 'lightning',
        '100': 'other',
        '5': None
    }

    activity_rate = {
        '150': 'activity_rate_150',
        '50': 'activity_rate_50',
        '30': 'activity_rate_30',
        '20': 'activity_rate_20',
        '10': 'activity_rate_10',
        '5': 'activity_rate_5',
        '1': 'activity_rate_1'
    }

    nb_outings = {
        '0': None,
        '4': 'nb_outings_4',
        '9': 'nb_outings_9',
        '14': 'nb_outings_14',
        '15': 'nb_outings_15',
    }

    gender = {
        '0': None,
        '1': 'male',
        '2': 'female'
    }

    previous_injuries = {
        '0': None,
        '1': 'no',
        '2': 'previous_injuries_2',
        '3': 'previous_injuries_3'
    }

    author_status = {
        '0': None,
        '1': 'primary_impacted',
        '2': 'secondary_impacted',
        '3': 'internal_witness',
        '4': 'external_witness',
    }

    severity = {
        '0': None,
        '1': 'serverity_no',
        '3': '1d_to_3d',
        '30': '4d_to_1m',
        '90': '1m_to_3m',
        '100': 'more_than_3m'
    }

    autonomy = {
        '0': None,
        '10': 'non_autonomous',
        '20': 'autonomous',
        '30': 'initiator',
        '40': 'expert',
        None: None
    }

    avalanche_level = {
        '0': None,
        '10': 'level_1',
        '20': 'level_2',
        '30': 'level_3',
        '40': 'level_4',
        '50': 'level_5',
        '100': 'level_na'
    }

    # invalid type: 39(3x), 45(1x), 42(?x)
    avalanche_slope = {
        '39': 'slope_39_41',
        '42': 'slope_42_44',
        '45': 'slope_45_47',
        '0': None,
        '29': 'slope_lt_30',
        '32': 'slope_30_32',
        '35': 'slope_33_35',
        '38': 'slope_36_38',
        '41': 'slope_39_41',
        '44': 'slope_42_44',
        '47': 'slope_45_47',
        '50': 'slope_gt_47'
    }
