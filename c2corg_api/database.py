"""
FastAPI database dependency.

Provides a ``get_db`` dependency that yields a SQLAlchemy session
backed by the same ``DBSession`` factory that Pyramid uses, but
**without** ``zope.sqlalchemy`` transaction management.

During the transitional period both stacks share the same engine;
only the session lifecycle differs:
  - Pyramid  → ``zope.sqlalchemy`` + ``pyramid_tm``
  - FastAPI  → explicit commit / rollback in the dependency
"""

from typing import Generator

from sqlalchemy.orm import Session, scoped_session, sessionmaker

# Will be configured at startup from the same engine as the Pyramid app.
_session_factory = sessionmaker()
FastAPISession: scoped_session = scoped_session(_session_factory)


def configure_db(engine) -> None:
    """Bind the FastAPI session factory to *engine*.

    Called once at application startup.
    """
    _session_factory.configure(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Yields a SQLAlchemy session that is committed when the request
    finishes successfully, or rolled back when an exception is raised.

    That way, if several database operations are performed in a single
    request, they are all committed or rolled back together.
    """
    db = FastAPISession()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        FastAPISession.remove()


# TODO: Drop scoped_session once Pyramid is removed.
# Using scoped_session gives you two benefits:

# Same mental model as Pyramid
# Same failure modes you already understand
# Less refactoring while Pyramid still exists

# But this is sync only
# SessionLocal = sessionmaker(bind=engine)

# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#         db.commit()
#     except Exception:
#         db.rollback()
#         raise
#     finally:
#         db.close()
