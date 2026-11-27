import logging

from c2corg_api.linkcheck.checker import REQUESTS_PER_RUN, run
from c2corg_api.models import DBSession

log = logging.getLogger(__name__)


def link_checker_enabled(settings):
    """Tell whether the scheduler checks the links (`link_checker.enabled`)."""
    value = str(settings.get('link_checker.enabled', 'false')).strip().lower()
    return value in ('true', '1', 'yes', 'on')


def check_links(settings):
    """Check the due links to other sites of the collaborative documents."""
    requests_per_run = int(
        settings.get('link_checker.requests_per_run') or REQUESTS_PER_RUN
    )
    run(DBSession.get_bind(), requests_per_run)
