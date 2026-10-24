from c2corg_api.tests.contract.inventory import (
    INVENTORY_FILE,
    format_inventory,
    route_inventory,
)


class TestRouteInventory:
    def test_routes_match_the_inventory(self, client):
        # routes.txt lists the public API: a route added, removed, or whose
        # methods or permission change must be reflected there, so the
        # change is visible in review. To update it:
        #   python -m c2corg_api.tests.contract.inventory
        actual = format_inventory(route_inventory(client.app.registry))
        with open(INVENTORY_FILE) as f:
            expected = f.read()
        assert actual == expected

    def test_only_explicit_methods(self, client):
        rows = route_inventory(client.app.registry)
        assert rows
        assert {method for _, method, _ in rows} <= {
            'GET',
            'POST',
            'PUT',
            'DELETE',
            'PATCH',
        }
