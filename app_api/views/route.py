from cornice.resource import resource, view
from sqlalchemy.orm import joinedload

from app_api.models.route import Route, schema_route
from app_api.models.document_history import HistoryMetaData, DocumentVersion
from app_api.models import DBSession
from . import validate_id, to_json_dict


@resource(collection_path='/routes', path='/routes/{id}')
class RouteRest(object):

    def __init__(self, request):
        self.request = request

    def collection_get(self):
        routes = DBSession. \
            query(Route). \
            options(joinedload(Route.locales)). \
            all()

        return [to_json_dict(wp, schema_route) for wp in routes]

    @view(validators=validate_id)
    def get(self):
        id = self.request.validated['id']

        route = DBSession. \
            query(Route). \
            filter(Route.document_id == id). \
            options(joinedload(Route.locales)). \
            first()

        return to_json_dict(route, schema_route)

    @view(schema=schema_route)
    def collection_post(self):
        route = schema_route.objectify(self.request.validated)

        DBSession.add(route)
        DBSession.flush()

        self._create_new_version(route)

        return to_json_dict(route, schema_route)

    def _create_new_version(self, route):
        """
        TODO This should be a generic function for all document types. Move
        into a more generic namespace and make `to_archive` and
        `get_archive_locales` abstract methods of `Document`.
        """
        archive_route = route.to_archive()
        archive_locales = route.get_archive_locales()

        meta_data = HistoryMetaData(is_minor=False, comment='creation')
        versions = []
        for locale in archive_locales:
            version = DocumentVersion(
                document_id=route.document_id,
                culture=locale.culture,
                version=1,
                nature='ft',
                document_archive=archive_route,
                document_i18n_archive=locale,
                history_metadata=meta_data
            )
            versions.append(version)

        DBSession.add(archive_route)
        DBSession.add_all(archive_locales)
        DBSession.add(meta_data)
        DBSession.add_all(versions)
        DBSession.flush()
