"""
FastAPI Waypoint-Stoparea router.

Provides:
  - ``GET /v2/waypoints/{waypoint_id}/stopareas``     – stopareas for a waypoint
  - ``GET /v2/waypoints/{waypoint_id}/isReachable``   – reachability check

Mirrors ``c2corg_api.views.waypoint_stoparea``.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import exists, func
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint_stoparea import WaypointStoparea

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/waypoints', tags=['waypoints_stopareas'])


# ── GET /v2/waypoints/{waypoint_id}/stopareas ────────────────


@router.get('/{waypoint_id}/stopareas')
def get_stopareas_for_waypoint(waypoint_id: int, db: Session = Depends(get_db)):
    """Return all stopareas associated with a waypoint,
    with their full attributes and distance."""
    query = (
        db.query(
            Stoparea,
            WaypointStoparea.distance,
            func.ST_X(Stoparea.geom).label('x'),
            func.ST_Y(Stoparea.geom).label('y'),
        )
        .join(WaypointStoparea, Stoparea.stoparea_id == WaypointStoparea.stoparea_id)
        .filter(WaypointStoparea.waypoint_id == waypoint_id)
        .all()
    )

    stopareas_data = [
        {**stoparea.to_dict(), 'distance': round(distance, 2)}
        for stoparea, distance, x, y in query
    ]

    return {'waypoint_id': waypoint_id, 'stopareas': stopareas_data}


# ── GET /v2/waypoints/{waypoint_id}/isReachable ─────────────


@router.get('/{waypoint_id}/isReachable')
def is_reachable(waypoint_id: int, db: Session = Depends(get_db)):
    """Return true if the waypoint has at least one associated stoparea."""
    has_stopareas = db.query(
        exists().where(WaypointStoparea.waypoint_id == waypoint_id)
    ).scalar()

    return has_stopareas
