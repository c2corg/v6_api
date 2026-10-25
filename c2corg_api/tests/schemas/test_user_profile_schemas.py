from c2corg_api.ext.colander_ext import wkbelement_from_geojson
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.user_profile import (
    UserProfile,
    schema_internal_user_profile,
    schema_listing_user_profile,
    schema_update_user_profile,
    schema_user_profile,
)
from c2corg_api.schemas.user_profile import (
    UserProfileUpdateSchema,
    internal_user_profile_schema,
    user_profile_listing_schema,
    user_profile_schema,
)
from c2corg_api.tests.schemas.parity import GEOMETRIES, assert_parity
from c2corg_api.views import serialize


def _profile():
    return UserProfile(
        document_id=1,
        version=2,
        activities=['hiking'],
        categories=['amateur'],
        locales=[DocumentLocale(lang='en', title='', version=1, description='Me')],
        geometry=DocumentGeometry(
            version=1, geom=wkbelement_from_geojson(GEOMETRIES['POINT'], 3857)
        ),
    )


def test_update_parity():
    assert_parity(schema_update_user_profile, UserProfileUpdateSchema)


def test_dictify():
    profile = _profile()
    for colander_schema, schema in (
        (schema_user_profile, user_profile_schema),
        (schema_internal_user_profile, internal_user_profile_schema),
        (schema_listing_user_profile, user_profile_listing_schema),
    ):
        assert serialize(schema.dictify(profile)) == serialize(
            colander_schema.dictify(profile)
        )


def test_objectify():
    data = {
        'document_id': 1,
        'version': 2,
        'locales': [{'lang': 'en', 'title': '', 'version': 1, 'description': 'Me'}],
        'activities': ['hiking'],
    }
    expected = schema_internal_user_profile.objectify(data)
    actual = internal_user_profile_schema.objectify(data)
    assert serialize(internal_user_profile_schema.dictify(actual)) == serialize(
        schema_internal_user_profile.dictify(expected)
    )
