from c2corg_api.tests.views import BaseTestRest


class _TestFundraiserMixin():

    def get(self, prefix, document_id):
        url = f"{prefix}/{document_id}"
        return self.app.get(url).json

    def post(self, document, status=200, username="contributor"):
        prefix = _type_to_prefix(document)

        assert "document_id" not in document

        headers = self.add_authorization_header(username=username)
        response = self.app_post_json(
            prefix, document, headers=headers, status=status
        ).json

        if status == 200:
            return self.get(prefix, response["document_id"])
        else:
            return None

    def put(self, document, username="contributor"):
        prefix = _type_to_prefix(document)
        url = f"{prefix}/{document['document_id']}"

        payload = {
            'message': 'Update',
            'document': document
        }

        headers = self.add_authorization_header(username=username)
        self.app_put_json(url, payload, headers=headers, status=200)
        result = self.get(prefix, document["document_id"])

        return result


class TestCreation(BaseTestRest, _TestFundraiserMixin):

    def test_area(self):
        area = self.post(_build_area(), username='moderator')
        assert area["fundraiser_url"] == "url"

    def test_waypoint(self):
        # Add an area that will contains the waypoint
        self.post(_build_area(), username='moderator')

        doc = _build_waypoint()

        waypoint = self.post(doc, username='moderator')
        assert waypoint["fundraiser_url"] == "url"
        assert waypoint["can_have_fundraiser"] is True
        assert waypoint["areas"][0]["fundraiser_url"] == "url"

        waypoint = self.post(doc, username='contributor')
        assert waypoint["fundraiser_url"] is None
        assert waypoint["can_have_fundraiser"] is True
        assert waypoint["areas"][0]["fundraiser_url"] == "url"

        doc = _build_waypoint(waypoint_type="summit")
        result = self.post(doc, username='moderator')
        assert result["fundraiser_url"] == "url"
        assert result["can_have_fundraiser"] is False
        assert result["areas"][0]["fundraiser_url"] == "url"

        doc = _build_waypoint(equipment_ratings=["P3"])
        result = self.post(doc, username='moderator')
        assert result["fundraiser_url"] == "url"
        assert result["can_have_fundraiser"] is False
        assert result["areas"][0]["fundraiser_url"] == "url"

    def test_route(self):
        # Add an area that will contains the waypoint
        self.post(_build_area(), username='moderator')
        wp = self.post(_build_waypoint(), username='moderator')

        result = self.post(_build_route(wp), username='moderator')
        assert result["fundraiser_url"] == "url"
        assert result["can_have_fundraiser"] is True
        assert result["areas"][0]["fundraiser_url"] == "url"
        assert result["associations"]["waypoints"][0]["fundraiser_url"] == "url"  # noqa
        assert result["associations"]["waypoints"][0]["can_have_fundraiser"] is True  # noqa

        result = self.post(_build_route(wp), username='contributor')
        assert result["fundraiser_url"] is None
        assert result["can_have_fundraiser"] is True
        assert result["areas"][0]["fundraiser_url"] == "url"
        assert result["associations"]["waypoints"][0]["fundraiser_url"] == "url"  # noqa

        doc = _build_route(wp, activities=["skitouring"])
        result = self.post(doc, username='moderator')
        assert result["fundraiser_url"] == "url"
        assert result["can_have_fundraiser"] is False
        assert result["areas"][0]["fundraiser_url"] == "url"
        assert result["associations"]["waypoints"][0]["fundraiser_url"] == "url"  # noqa

        doc = _build_route(wp, activities=["skitouring"])
        result = self.post(doc, username='contributor')
        assert result["fundraiser_url"] is None
        assert result["can_have_fundraiser"] is False
        assert result["areas"][0]["fundraiser_url"] == "url"
        assert result["associations"]["waypoints"][0]["fundraiser_url"] == "url"  # noqa


class TestEdition(BaseTestRest, _TestFundraiserMixin):

    def test_area(self):
        area = self.post(_build_area(), username='moderator')

        area["fundraiser_url"] = "other url"
        del area["geometry"]
        area = self.put(area, username='contributor')
        assert area["fundraiser_url"] == "url"

        area["fundraiser_url"] = "other url"
        area = self.put(area, username='moderator')
        assert area["fundraiser_url"] == "other url"

    def test_waypoint(self):
        area = self.post(_build_area(), username='moderator')
        waypoint = self.post(_build_waypoint(), username='moderator')

        waypoint["fundraiser_url"] = "other url"
        waypoint = self.put(waypoint, username='contributor')
        assert waypoint["fundraiser_url"] == "url"

        waypoint["fundraiser_url"] = "other url"
        waypoint = self.put(waypoint, username='moderator')
        assert waypoint["fundraiser_url"] == "other url"

        area["fundraiser_url"] = "other url for area"
        self.put(area, username='moderator')
        waypoint = self.get("/waypoints", waypoint["document_id"])
        assert waypoint["areas"][0]["fundraiser_url"] == "other url for area"

        # even if can_have_fundraiser is false, we keep the value: as only
        # moderators can change it, if the value was lost, it means that a
        # regular contributor could remove it by changing the wp type, and
        # set it back.
        waypoint["waypoint_type"] = "summit"
        waypoint = self.put(waypoint)
        assert waypoint["fundraiser_url"] == "other url"
        assert waypoint["can_have_fundraiser"] is False

        waypoint["waypoint_type"] = "climbing_outdoor"
        waypoint["equipment_ratings"] = ["P1"]  # this value has been lost during the previsous change  # noqa
        waypoint = self.put(waypoint)
        assert waypoint["fundraiser_url"] == "other url"
        assert waypoint["can_have_fundraiser"] is True

        waypoint["equipment_ratings"] = ["P3"]
        waypoint = self.put(waypoint)
        assert waypoint["fundraiser_url"] == "other url"
        assert waypoint["can_have_fundraiser"] is False

        waypoint["equipment_ratings"] = ["P1"]
        waypoint = self.put(waypoint)
        assert waypoint["fundraiser_url"] == "other url"
        assert waypoint["can_have_fundraiser"] is True

    def test_route(self):
        area = self.post(_build_area(), username='moderator')
        waypoint = self.post(_build_waypoint(), username='moderator')
        route = self.post(_build_route(waypoint), username='moderator')

        route["fundraiser_url"] = "other url"
        route = self.put(route, username='contributor')
        assert route["fundraiser_url"] == "url"

        route["fundraiser_url"] = "other url"
        route = self.put(route, username='moderator')
        assert route["fundraiser_url"] == "other url"

        area["fundraiser_url"] = "other url for area"
        self.put(area, username='moderator')
        route = self.get("/routes", route["document_id"])
        assert route["areas"][0]["fundraiser_url"] == "other url for area"

        waypoint["fundraiser_url"] = "other url for waypoint"
        waypoint = self.put(waypoint, username='moderator')
        route = self.get("/routes", route["document_id"])
        assert route["associations"]["waypoints"][0]["fundraiser_url"] == "other url for waypoint"  # noqa

        waypoint["waypoint_type"] = "summit"
        waypoint = self.put(waypoint)
        route = self.get("/routes", route["document_id"])
        assert route["associations"]["waypoints"][0]["fundraiser_url"] == "other url for waypoint"  # noqa
        assert route["associations"]["waypoints"][0]["can_have_fundraiser"] is False  # noqa

        waypoint["waypoint_type"] = "climbing_outdoor"
        waypoint["equipment_ratings"] = ["P1"]  # this value has been lost during the previsous change  # noqa
        waypoint = self.put(waypoint)
        route = self.get("/routes", route["document_id"])
        assert route["associations"]["waypoints"][0]["fundraiser_url"] == "other url for waypoint"  # noqa
        assert route["associations"]["waypoints"][0]["can_have_fundraiser"] is True  # noqa

        route["activities"] = ["skitouring"]
        route = self.put(route)
        assert route["fundraiser_url"] == "other url"
        assert route["can_have_fundraiser"] is False

        route["activities"] = ["rock_climbing"]
        route = self.put(route)
        assert route["fundraiser_url"] == "other url"
        assert route["can_have_fundraiser"] is True


class TestHistory(BaseTestRest, _TestFundraiserMixin):
    def get_versions(self, document):
        document_id = document['document_id']
        prefix = _type_to_prefix(document)

        history = self.app.get(f"/document/{document_id}/history/en").json

        return [
            self.app.get(f"{prefix}/{document_id}/en/{version['version_id']}").json  # noqa
            for version in history["versions"]
        ]

    def test_history(self):
        self._test_history(_build_area())

    def test_waypoint(self):
        self._test_history(_build_waypoint())

    def test_route(self):
        waypoint = self.post(_build_waypoint())
        self._test_history(_build_route(waypoint))

    def _test_history(self, document):
        document = self.post(document, username='moderator')

        document["fundraiser_url"] = "other url"
        document = self.put(document, username='moderator')

        versions = self.get_versions(document)
        assert versions[0]['document']['fundraiser_url'] == "url"
        assert versions[1]['document']['fundraiser_url'] == "other url"

        return document


def _type_to_prefix(document):
    return {
        'r': '/routes',
        'a': '/areas',
        'w': '/waypoints',
    }[document['type']]


def _build_area():
    return {
        'area_type': 'range',
        'geometry': {
            'id': 5678, 'version': 6789,
            'geom_detail': '{"type":"Polygon","coordinates":[[[0,0],[0,2],[2,2],[2,0],[0,0]]]}'  # noqa
        },
        'locales': [
            {'lang': 'en', 'title': 'Chartreuse'}
        ],
        'fundraiser_url': 'url',
        'type': 'a'
    }


def _build_waypoint(**kwargs):
    doc = {
        'waypoint_type': 'climbing_outdoor',
        'equipment_ratings': ["P1+"],
        'geometry': {
            'id': 5678, 'version': 6789,
            'geom': '{"type":"Point","coordinates":[1, 1]}'
        },
        'locales': [
            {'lang': 'en', 'title': 'Chartreuse'}
        ],
        "elevation": 4,
        'fundraiser_url': 'url',
        'type': 'w'
    }

    return {**doc, **kwargs}


def _build_route(waypoint, **kwargs):
    doc = {
        'activities': ['rock_climbing'],
        'associations': {
            'waypoints': [waypoint]
        },
        'geometry': {
            'id': 5678, 'version': 6789,
            'geom': '{"type":"Point","coordinates":[1, 1]}'
        },
        'locales': [
            {'lang': 'en', 'title': 'Chartreuse'}
        ],
        'fundraiser_url': 'url',
        'type': 'r'
    }

    return {**doc, **kwargs}
