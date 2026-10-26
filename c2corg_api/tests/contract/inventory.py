"""Inventory of the public routes of the API, with their methods and permission."""

import os
import sys

# the file the inventory is compared with (see test_inventory.py)
INVENTORY_FILE = os.path.join(os.path.dirname(__file__), 'routes.txt')

# methods every route answers without a view of its own: Cornice adds a
# catch-all view ('*', 405) and the CORS preflight (OPTIONS), Pyramid
# answers HEAD with the GET view
IMPLICIT_METHODS = {'*', 'OPTIONS', 'HEAD'}

# the permission of a view that has none
PUBLIC = 'public'


def route_inventory(registry):
    """Return the routes as sorted (path, method, permission) tuples."""
    introspector = registry.introspector
    rows = set()
    for route in introspector.get_category('routes'):
        pattern = route['introspectable']['pattern']
        for view in route['related']:
            if view.category_name != 'views':
                continue
            methods = view['request_methods'] or ('*',)
            if isinstance(methods, str):
                methods = (methods,)
            permissions = [
                p['value']
                for p in introspector.related(view)
                if p.category_name == 'permissions'
            ]
            permission = permissions[0] if permissions else PUBLIC
            for method in methods:
                if method not in IMPLICIT_METHODS:
                    rows.add((pattern, method, permission))
    return sorted(rows)


def format_inventory(rows):
    """Format the inventory as the lines of `routes.txt`."""
    return ''.join(
        f'{method:<7} {path}  [{permission}]\n' for path, method, permission in rows
    )


def main():
    """Write the inventory of the test application to `routes.txt`."""
    # usage: python -m c2corg_api.tests.contract.inventory
    from c2corg_api import main as make_app
    from c2corg_api.tests import settings

    app = make_app({}, **settings)
    with open(INVENTORY_FILE, 'w') as f:
        f.write(format_inventory(route_inventory(app.registry)))
    sys.stdout.write(f'{INVENTORY_FILE} written\n')


if __name__ == '__main__':
    main()
