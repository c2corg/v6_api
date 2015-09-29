from cornice.resource import resource, view
from sqlalchemy.orm import joinedload, contains_eager

from c2corg_api.models.waypoint import Waypoint, schema_waypoint
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models import DBSession
from c2corg_api.views.document import DocumentRest
from c2corg_api.views import validate_id, to_json_dict


@resource(collection_path='/waypoints', path='/waypoints/{id}')
class WaypointRest(DocumentRest):

    def collection_get(self):
        waypoints = DBSession. \
            query(Waypoint). \
            options(joinedload(Waypoint.locales)). \
            limit(30)

        return [to_json_dict(wp, schema_waypoint) for wp in waypoints]

    @view(validators=validate_id)
    def get(self):
        id = self.request.validated['id']
        culture = self.request.GET.get('l')

        if not culture:
            waypoint = DBSession. \
                query(Waypoint). \
                filter(Waypoint.document_id == id). \
                options(joinedload(Waypoint.locales)). \
                first()
        else:
            waypoint = DBSession. \
                query(Waypoint). \
                join(Waypoint.locales). \
                filter(Waypoint.document_id == id). \
                options(contains_eager(Waypoint.locales)). \
                filter(DocumentLocale.culture == culture). \
                first()

        return to_json_dict(waypoint, schema_waypoint)

    @view(schema=schema_waypoint)
    def collection_post(self):
        waypoint = schema_waypoint.objectify(self.request.validated)

        DBSession.add(waypoint)
        DBSession.flush()

        self._create_new_version(waypoint)

        return to_json_dict(waypoint, schema_waypoint)
