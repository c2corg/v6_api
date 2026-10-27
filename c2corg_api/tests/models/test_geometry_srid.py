from geoalchemy2.types import Geometry
from sqlalchemy import text

# imported for their tables
import c2corg_api.models.stoparea  # noqa: F401
import c2corg_api.models.waypoint_stoparea  # noqa: F401
from c2corg_api.models import Base
from c2corg_api.tests import BaseTestCase


class TestGeometrySrid(BaseTestCase):
    def test_models_have_the_srid_of_the_database(self):
        # the test database is built by the migrations, as in production
        mismatches = []
        for table in Base.metadata.sorted_tables:
            for column in table.columns:
                if not isinstance(column.type, Geometry):
                    continue
                srid = self.session.execute(
                    text('SELECT Find_SRID(:schema, :table, :column)'),
                    {
                        'schema': table.schema,
                        'table': table.name,
                        'column': column.name,
                    },
                ).scalar()
                if srid != column.type.srid:
                    mismatches.append((table.fullname, column.name, srid))
        assert mismatches == []
