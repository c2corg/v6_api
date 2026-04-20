"""
Pure document helpers extracted from ``c2corg_api.views.__init__``.

These functions have **no** Pyramid / Cornice dependency.  Router code
should import from here instead of from ``c2corg_api.views``.
"""

import logging

from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from c2corg_api.models.common.attributes import langs_priority
from c2corg_api.models.dictify import dictify as sa_dictify
from c2corg_api.models.document_history import get_creators
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.routers.helpers.markdown import cook

log = logging.getLogger(__name__)


# NOTE: to_json_dict is no longer used in production router code.
# It remains here only for test_to_json_dict.py and
# test_listing_schema_equivalence.py snapshot/equivalence tests.
# Once the legacy ``views/`` layer is removed, this function and the
# ``sa_dictify`` import can be deleted.
def to_json_dict(
    obj,
    schema,
    with_special_locales_attrs=False,
    with_special_geometry_attrs=False,
    cook_locale=False,
):
    obj_dict = sa_dictify(obj, schema)
    # manually copy certain attributes that were set on the object
    # (these are not real SA columns, so they are not in the field spec)
    special_attributes = [
        'available_langs',
        'associations',
        'maps',
        'areas',
        'author',
        'protected',
        'type',
        'name',
        'forum_username',
        'creator',
        'img_count',
    ]
    for attr in special_attributes:
        if hasattr(obj, attr):
            obj_dict[attr] = getattr(obj, attr)

    locale_special_attributes = ['topic_id']
    if with_special_locales_attrs and hasattr(obj, 'locales'):
        for i in range(0, len(obj.locales)):
            locale = obj.locales[i]
            locale_dict = obj_dict['locales'][i]
            for attr in locale_special_attributes:
                if hasattr(locale, attr):
                    locale_dict[attr] = getattr(locale, attr)

    if cook_locale:
        obj_dict['cooked'] = cook(obj_dict['locales'][0])

    if with_special_geometry_attrs and obj.type in (ROUTE_TYPE, OUTING_TYPE):
        geometry_special_attributes = ['has_geom_detail']
        geometry_dict = obj_dict['geometry']
        geometry = obj.geometry
        for attr in geometry_special_attributes:
            if hasattr(geometry, attr):
                geometry_dict[attr] = getattr(geometry, attr)
    return obj_dict


def set_best_locale(documents, preferred_lang, expunge=True, *, db: Session):
    """Sets the "best" locale on the given documents. The "best" locale is
    the locale in the given "preferred language" if available. Otherwise
    it is the "most relevant" translation according to `langs_priority`.
    """
    if preferred_lang is None:
        return

    for document in documents:
        # need to detach the document from the session, so that the
        # following change to `document.locales` is not persisted
        if expunge and not inspect(document).detached:
            if db is None:
                raise ValueError('db session required for expunge')
            db.expunge(document)

        if document.locales:
            available_locales = {locale.lang: locale for locale in document.locales}
            best_locale = get_best_locale(available_locales, preferred_lang)
            if best_locale:
                document.locales = [best_locale]


def get_best_locale(available_locales, preferred_lang):
    if preferred_lang in available_locales:
        best_locale = available_locales[preferred_lang]
    else:
        best_locale = next(
            (
                available_locales[lang]
                for lang in langs_priority
                if lang in available_locales
            ),
            None,
        )
    return best_locale


def set_creator(documents, field_name):
    """Set the creator (the user who created the first version of a document)
    on a list of documents.
    """
    if not documents:
        return
    document_ids = [o.document_id for o in documents]

    author_for_documents = get_creators(document_ids)

    for document in documents:
        setattr(document, field_name, author_for_documents.get(document.document_id))


def set_author(outings, lang):
    """Set the author (the user who created an outing) on a list of
    outings.
    """
    set_creator(outings, 'author')
