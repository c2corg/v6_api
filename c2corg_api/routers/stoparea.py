"""
FastAPI Stoparea router.

Provides:
  - ``GET /v2/stopareas``          – paginated list
  - ``GET /v2/stopareas/{id}``     – single stoparea
  - ``GET /v2/stopareas/{id}/{lang}/info`` – info view

Mirrors ``c2corg_api.views.stoparea``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.stoparea import Stoparea

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/stopareas', tags=['stopareas'])


# ── GET /v2/stopareas ────────────────────────────────────────


@router.get('')
def collection_get(
    page_id: int = Query(1, ge=1),
    nb_items: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Return a paginated list of stopareas."""
    query = db.query(Stoparea)
    total_results = query.count()

    stopareas = query.offset((page_id - 1) * nb_items).limit(nb_items).all()

    return {
        'documents': [s.to_dict() for s in stopareas],
        'total_results': total_results,
    }


# ── GET /v2/stopareas/{id} ───────────────────────────────────


@router.get('/{stoparea_id}')
def get_stoparea(stoparea_id: int, db: Session = Depends(get_db)):
    """Return a single stoparea."""
    stoparea = db.query(Stoparea).filter(Stoparea.stoparea_id == stoparea_id).first()
    if not stoparea:
        raise HTTPException(status_code=404, detail='Stoparea not found')

    return stoparea.to_dict()


# ── GET /v2/stopareas/{id}/{lang}/info ───────────────────────


@router.get('/{stoparea_id}/{lang}/info')
def get_stoparea_info(stoparea_id: int, lang: str, db: Session = Depends(get_db)):
    """Return basic info for a stoparea (used by UI for URL slugs)."""
    stoparea = db.query(Stoparea).filter(Stoparea.stoparea_id == stoparea_id).first()
    if not stoparea:
        raise HTTPException(status_code=404, detail='Stoparea not found')

    return {
        'stoparea_id': stoparea.stoparea_id,
        'attributes': {
            'navitia_id': stoparea.navitia_id,
            'stoparea_name': stoparea.stoparea_name,
            'line': stoparea.line,
            'operator': stoparea.operator,
            'geom': str(stoparea.geom),
        },
    }
