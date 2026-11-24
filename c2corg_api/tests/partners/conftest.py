import os

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip the `partner_live` tests unless PARTNER_LIVE=1.

    `-m "not partner_live"` is in the default options, so they are not even
    collected by a plain `pytest`; `-m partner_live` selects them, and they are
    then skipped with a reason unless the opt-in variable is set.
    """
    if os.environ.get('PARTNER_LIVE') == '1':
        return
    skip = pytest.mark.skip(reason='live partner tests: set PARTNER_LIVE=1')
    for item in items:
        if 'partner_live' in item.keywords:
            item.add_marker(skip)
