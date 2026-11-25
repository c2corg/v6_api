"""Layer 3: the real adapters against the real partner sites (opt in).

    PARTNER_LIVE=1 uv run pytest -m partner_live c2corg_api/tests/partners

Skipped by default and in CI. A site that blocks or does not answer, or a
missing key, skips the test with the reason: that is availability, not a
contract change. What fails is a field the adapter reads that went missing or
changed type, or an answer the adapter cannot parse.
"""

import datetime

import pytest

from c2corg_api.partners import contract
from c2corg_api.partners.__main__ import DEFAULT_FIXTURES, secrets_from_env
from c2corg_api.partners.adapter import SourceBlocked, SourceDisabled, SourceDown
from c2corg_api.partners.sources import REGISTRY
from c2corg_api.partners.transport import HttpTransport

pytestmark = pytest.mark.partner_live


@pytest.mark.parametrize('source', sorted(REGISTRY))
def test_live_contract(source):
    adapter = REGISTRY[source]()
    capture = contract.CapturingTransport(HttpTransport(adapter.rate))
    since = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=2)
    try:
        contract.run_adapter(adapter, capture, secrets_from_env(adapter), since)
    except SourceDisabled as e:
        pytest.skip(f'{source} disabled: {e}')
    except SourceBlocked as e:
        pytest.skip(f'{source} blocked: {e}')
    except SourceDown as e:
        pytest.skip(f'{source} down: {e}')

    actual = contract.captured_shapes(source, capture.responses)
    if not actual:
        pytest.skip(f'{source}: no answer to check')
    expected = contract.fixture_shapes(DEFAULT_FIXTURES / source)
    report = contract.compare(adapter, expected, actual)
    for diff in report.diff.values():  # shown with -s or on failure
        print('\n'.join(diff))
    assert not report.problems, '\n'.join(report.problems)
