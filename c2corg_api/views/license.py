"""Licence under which a document is published."""

from c2corg_api.models.common.document_types import (
    AREA_TYPE,
    ARTICLE_TYPE,
    BOOK_TYPE,
    IMAGE_TYPE,
    OUTING_TYPE,
    ROUTE_TYPE,
    USERPROFILE_TYPE,
    WAYPOINT_TYPE,
    XREPORT_TYPE,
)

CC_BY_SA = {
    'id': 'CC-BY-SA-3.0',
    'url': 'https://creativecommons.org/licenses/by-sa/3.0/',
}
CC_BY_NC_ND = {
    'id': 'CC-BY-NC-ND-3.0',
    'url': 'https://creativecommons.org/licenses/by-nc-nd/3.0/',
}
COPYRIGHT = {
    'id': 'copyright',
    'url': 'https://www.camptocamp.org/articles/106728',
}

# collaborative documents are BY-SA, personal ones BY-NC-ND
_LICENSE_BY_TYPE = {
    AREA_TYPE: CC_BY_SA,
    BOOK_TYPE: CC_BY_SA,
    ROUTE_TYPE: CC_BY_SA,
    WAYPOINT_TYPE: CC_BY_SA,
    OUTING_TYPE: CC_BY_NC_ND,
    USERPROFILE_TYPE: CC_BY_NC_ND,
    XREPORT_TYPE: CC_BY_NC_ND,
}
_ARTICLE_LICENSES = {'collab': CC_BY_SA, 'personal': CC_BY_NC_ND}
_IMAGE_LICENSES = {
    'collaborative': CC_BY_SA,
    'personal': CC_BY_NC_ND,
    'copyright': COPYRIGHT,
}

# the path of each document type in the UI
_UI_PATHS = {
    AREA_TYPE: 'areas',
    ARTICLE_TYPE: 'articles',
    BOOK_TYPE: 'books',
    IMAGE_TYPE: 'images',
    OUTING_TYPE: 'outings',
    ROUTE_TYPE: 'routes',
    USERPROFILE_TYPE: 'profiles',
    WAYPOINT_TYPE: 'waypoints',
    XREPORT_TYPE: 'xreports',
}

_ui_url = None


def configure_license(settings):
    """Read the UI URL, used to link the history page of a document."""
    global _ui_url
    _ui_url = (settings.get('ui.url') or '').rstrip('/') or None


def get_license(document_type, document):
    """Return the licence of a serialized document, or None if it has none."""
    # topo maps and coverages are not user content: they have no licence
    if document_type == ARTICLE_TYPE:
        doc_license = _ARTICLE_LICENSES.get(document.get('article_type'))
    elif document_type == IMAGE_TYPE:
        doc_license = _IMAGE_LICENSES.get(document.get('image_type'))
    else:
        doc_license = _LICENSE_BY_TYPE.get(document_type)
    if not doc_license:
        return None

    doc_license = dict(doc_license)
    attribution_url = _get_attribution_url(document_type, document)
    if attribution_url:
        doc_license['attribution_url'] = attribution_url
    return doc_license


def _get_attribution_url(document_type, document):
    # the contributors (the "BY" of the licence) are listed in the history
    # page of the document, which exists per language
    locales = document.get('locales')
    document_id = document.get('document_id')
    if not _ui_url or not locales or not document_id:
        return None
    lang = locales[0].get('lang')
    if not lang:
        return None
    return f'{_ui_url}/{_UI_PATHS[document_type]}/history/{document_id}/{lang}'
