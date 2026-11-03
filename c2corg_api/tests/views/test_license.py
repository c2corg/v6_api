import pytest

from c2corg_api.models.common.document_types import (
    AREA_TYPE,
    ARTICLE_TYPE,
    BOOK_TYPE,
    COVERAGE_TYPE,
    IMAGE_TYPE,
    MAP_TYPE,
    OUTING_TYPE,
    ROUTE_TYPE,
    USERPROFILE_TYPE,
    WAYPOINT_TYPE,
    XREPORT_TYPE,
)
from c2corg_api.tests import settings
from c2corg_api.views.license import configure_license, get_license

BY_SA = 'CC-BY-SA-3.0'
BY_NC_ND = 'CC-BY-NC-ND-3.0'


@pytest.fixture(autouse=True)
def ui_url():
    configure_license({'ui.url': 'https://www.camptocamp.org/'})
    yield
    configure_license(settings)


def _doc(**attrs):
    return {'document_id': 42, 'locales': [{'lang': 'fr'}], **attrs}


@pytest.mark.parametrize(
    'document_type,attrs,expected',
    [
        (AREA_TYPE, {}, BY_SA),
        (BOOK_TYPE, {}, BY_SA),
        (ROUTE_TYPE, {}, BY_SA),
        (WAYPOINT_TYPE, {}, BY_SA),
        (OUTING_TYPE, {}, BY_NC_ND),
        (USERPROFILE_TYPE, {}, BY_NC_ND),
        (XREPORT_TYPE, {}, BY_NC_ND),
        (ARTICLE_TYPE, {'article_type': 'collab'}, BY_SA),
        (ARTICLE_TYPE, {'article_type': 'personal'}, BY_NC_ND),
        (IMAGE_TYPE, {'image_type': 'collaborative'}, BY_SA),
        (IMAGE_TYPE, {'image_type': 'personal'}, BY_NC_ND),
        (IMAGE_TYPE, {'image_type': 'copyright'}, 'copyright'),
    ],
)
def test_license(document_type, attrs, expected):
    assert get_license(document_type, _doc(**attrs))['id'] == expected


@pytest.mark.parametrize(
    'document_type,attrs',
    [
        (MAP_TYPE, {}),
        (COVERAGE_TYPE, {}),
        # the type is not loaded
        (ARTICLE_TYPE, {}),
        (IMAGE_TYPE, {}),
    ],
)
def test_no_license(document_type, attrs):
    assert get_license(document_type, _doc(**attrs)) is None


def test_license_urls():
    assert get_license(ROUTE_TYPE, _doc()) == {
        'id': BY_SA,
        'url': 'https://creativecommons.org/licenses/by-sa/3.0/',
        'attribution_url': 'https://www.camptocamp.org/routes/history/42/fr',
    }
    assert get_license(IMAGE_TYPE, _doc(image_type='copyright')) == {
        'id': 'copyright',
        'url': 'https://www.camptocamp.org/articles/106728',
        'attribution_url': 'https://www.camptocamp.org/images/history/42/fr',
    }


def test_attribution_url_of_profile():
    assert (
        get_license(USERPROFILE_TYPE, _doc())['attribution_url']
        == 'https://www.camptocamp.org/profiles/history/42/fr'
    )


def test_no_attribution_url_without_locale():
    assert 'attribution_url' not in get_license(ROUTE_TYPE, _doc(locales=[]))


def test_no_attribution_url_without_ui_url():
    configure_license({})
    assert get_license(ROUTE_TYPE, _doc()) == {
        'id': BY_SA,
        'url': 'https://creativecommons.org/licenses/by-sa/3.0/',
    }


def test_license_is_a_copy():
    get_license(ROUTE_TYPE, _doc())['id'] = 'changed'
    assert get_license(ROUTE_TYPE, _doc())['id'] == BY_SA
