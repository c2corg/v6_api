import transaction
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.document import DocumentGeometry, \
    ArchiveDocumentGeometry
from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import Route, RouteLocale, ArchiveRoute, \
    ArchiveRouteLocale, ROUTE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.scripts.migration.batch import SimpleBatch
from c2corg_api.scripts.migration.documents.batch_document import DocumentBatch
from sqlalchemy.sql import text
import zope

from c2corg_api.scripts.migration.migrate_base import MigrateBase


class CreateClimbingSiteRoutes(MigrateBase):
    """In v5 it was possible to associate outings directly to climbing sites.
    In v6 associations between waypoints and outings are no longer possible.
    Instead a dummy route is created for climbing sites that have direct
    associations with outings.

    See also: https://github.com/c2corg/v6_api/issues/351
    """

    def migrate(self):
        self.start('dummy routes for climbing sites')

        with transaction.manager:
            climbing_sites = self._get_climbing_sites()
            print(
                'Creating dummy routes for {} climbing sites'.format(
                    len(climbing_sites)))

            # create dummy routes for climbing sites
            links_for_climbing_site = self._create_dummy_routes(
                climbing_sites)

            # create associations between the dummy routes and the climbing
            # sites, and also with the outings
            self._create_links_for_routes(links_for_climbing_site)

            # remove all waypoint-outing associations
            self._remove_waypoint_outing_links()

            zope.sqlalchemy.mark_changed(self.session_target)

        self.stop()

    def _get_climbing_sites(self):
        query = text(SQL_GET_CLIMBING_SITES)
        return [
            (c.waypoint_id, c.outing_ids, c.elevation)
            for c in self.session_target.execute(query)
        ]

    def _create_dummy_routes(self, climbing_sites):
        route_batch = DocumentBatch(
            self.session_target, self.batch_size,
            Route, ArchiveRoute,
            DocumentGeometry, ArchiveDocumentGeometry)
        route_locale_batch = DocumentBatch(
            self.session_target, self.batch_size,
            RouteLocale, ArchiveRouteLocale,
            None, None)
        history_batch = SimpleBatch(
            self.session_target, self.batch_size, HistoryMetaData)
        version_batch = SimpleBatch(
            self.session_target, self.batch_size, DocumentVersion)

        with route_batch:
            links_for_climbing_site, route_locales, route_locale_archives, \
                history_entries, version_entries = \
                self._create_routes(climbing_sites, route_batch)

        with route_locale_batch:
            for route_locale in route_locales:
                route_locale_batch.add_document(route_locale)
            for route_locale_archive in route_locale_archives:
                route_locale_batch.add_archive_documents(
                    [route_locale_archive])

        with history_batch:
            for entry in history_entries:
                history_batch.add(entry)

        with version_batch:
            for entry in version_entries:
                version_batch.add(entry)

        return links_for_climbing_site

    def _create_routes(self, climbing_site_ids, route_batch):
        routes_ids = RouteIds(self.session_target)

        links_for_climbing_site = {}
        history_entries = []
        version_entries = []
        route_locales = []
        route_locale_archives = []
        for (climbing_site_id, outings_ids, elevation) in climbing_site_ids:
            route_id, route_archive_id, route_geometry_archive_id, \
                route_locale_id, route_locale_archive_id, history_id, \
                version_id = routes_ids.get_ids()

            links_for_climbing_site[climbing_site_id] = (route_id, outings_ids)

            route = dict(
                document_id=route_id,
                type=ROUTE_TYPE,
                version=1,
                protected=False,
                activities=['hiking'],
                main_waypoint_id=climbing_site_id,
                quality='empty',
                route_types=['return_same_way'],
                durations=['1'],
                elevation_max=elevation
            )
            route_batch.add_document(route)

            route_archive = dict(route)
            route_archive['id'] = route_archive_id
            route_batch.add_archive_documents([route_archive])

            # create an empty geometry, it will be filled when setting
            # default geometries
            route_geometry = dict(
                document_id=route_id,
                version=1
            )
            route_batch.add_geometry(route_geometry)

            route_geometry_archive = dict(route_geometry)
            route_geometry_archive['id'] = route_geometry_archive_id
            route_batch.add_geometry_archives([route_geometry_archive])

            route_locale = dict(
                document_id=route_id,
                id=route_locale_id,
                type=ROUTE_TYPE,
                version=1,
                lang='fr',
                title='Accès pédestre',
                description='[[articles/822764/fr|Info]]',
            )
            route_locales.append(route_locale)

            route_locale_archive = dict(route_locale)
            route_locale_archive['id'] = route_locale_archive_id
            route_locale_archives.append(route_locale_archive)

            history = dict(
                id=history_id,
                user_id=2,  # c2c user
                comment='Auto-create climbing site route'
            )
            history_entries.append(history)

            version = dict(
                id=version_id,
                document_id=route_id,
                lang='fr',
                document_archive_id=route_archive_id,
                document_locales_archive_id=route_locale_archive_id,
                document_geometry_archive_id=route_geometry_archive_id,
                history_metadata_id=history_id
            )
            version_entries.append(version)

        return \
            links_for_climbing_site, route_locales, route_locale_archives, \
            history_entries, version_entries

    def _create_links_for_routes(self, links_for_climbing_site):
        association_batch = SimpleBatch(
            self.session_target, self.batch_size, Association)
        association_log_batch = SimpleBatch(
            self.session_target, self.batch_size, AssociationLog)

        with association_batch, association_log_batch:
            for climbing_site_id in links_for_climbing_site:
                route_id, outings_ids = \
                    links_for_climbing_site[climbing_site_id]

                # create association between fake route and climbing site
                link_site_route = dict(
                    parent_document_id=climbing_site_id,
                    parent_document_type=WAYPOINT_TYPE,
                    child_document_id=route_id,
                    child_document_type=ROUTE_TYPE
                )
                association_batch.add(link_site_route)

                link_site_route_log = dict(link_site_route)
                link_site_route_log['user_id'] = 2  # c2c user
                association_log_batch.add(link_site_route_log)

                # create associations between fake route and outings
                for outing_id in outings_ids:
                    link_outing_route = dict(
                        parent_document_id=route_id,
                        parent_document_type=ROUTE_TYPE,
                        child_document_id=outing_id,
                        child_document_type=OUTING_TYPE
                    )
                    association_batch.add(link_outing_route)

                    link_outing_route_log = dict(link_outing_route)
                    link_outing_route_log['user_id'] = 2  # c2c user
                    association_log_batch.add(link_outing_route_log)

    def _remove_waypoint_outing_links(self):
        self.session_target.execute(SQL_DELETE_WP_OUTING_LINKS)
        self.session_target.execute(SQL_DELETE_WP_OUTING_LOGS_LINKS)


# climbing sites that need a fake route: climbing sites that associated to an
# outing, which has no association with another route.
# only climbing sites are directly linked outings, no other waypoint types.
SQL_GET_CLIMBING_SITES = """
with climbing_sites as (select
  a.parent_document_id as waypoint_id,
  array_agg(a.child_document_id) as outing_ids
from guidebook.associations a
where parent_document_type = 'w' and child_document_type = 'o'
group by waypoint_id)
select c.waypoint_id, c.outing_ids, w.elevation
from climbing_sites c join guidebook.waypoints w
  on c.waypoint_id = w.document_id;
"""

SQL_DELETE_WP_OUTING_LINKS = """
DELETE FROM guidebook.associations
WHERE
  parent_document_type = 'w' and
  child_document_type = 'o';
"""

SQL_DELETE_WP_OUTING_LOGS_LINKS = """
DELETE FROM guidebook.association_log
WHERE
  parent_document_type = 'w' and
  child_document_type = 'o';
"""


class RouteIds(object):

    def __init__(self, session_target):
        self.current_route_id = get_last_id(
            session_target, 'documents', 'document_id')
        self.current_route_archive_id = get_last_id(
            session_target, 'documents_archives', 'id')
        self.current_route_geometry_archive_id = get_last_id(
            session_target, 'documents_geometries_archives', 'id')
        self.current_route_locale_id = get_last_id(
            session_target, 'documents_locales', 'id')
        self.current_route_locale_archive_id = get_last_id(
            session_target, 'documents_locales_archives', 'id')
        self.current_history_id = get_last_id(
            session_target, 'history_metadata', 'id')
        self.current_version_id = get_last_id(
            session_target, 'documents_versions', 'id')

    def get_ids(self):
        self.current_route_id += 1
        self.current_route_archive_id += 1
        self.current_route_geometry_archive_id += 1
        self.current_route_locale_id += 1
        self.current_route_locale_archive_id += 1
        self.current_history_id += 1
        self.current_version_id += 1

        return (
            self.current_route_id,
            self.current_route_archive_id,
            self.current_route_geometry_archive_id,
            self.current_route_locale_id,
            self.current_route_locale_archive_id,
            self.current_history_id,
            self.current_version_id
        )


def get_last_id(session_target, table, id_column):
    sql = 'select max({2}) from {0}.{1}'.format('guidebook', table, id_column)
    query = text(sql)
    return session_target.execute(query).first()[0]
