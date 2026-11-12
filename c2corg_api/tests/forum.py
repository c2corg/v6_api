"""The Discourse client of the API, faked for the tests."""

from unittest.mock import MagicMock, Mock

from c2corg_api.security.discourse_client import (
    APIDiscourseClient,
    get_discourse_client,
    set_discourse_client,
)


class FakeDiscourse:
    """Switch the Discourse client the API uses: up, down, or another one."""

    def __init__(self, settings):
        self.settings = settings
        self.original = get_discourse_client(settings)
        self.client = None
        self.up()

    def use(self, client):
        """Make the API use this client."""
        self.client = client
        set_discourse_client(client)

    def up(self):
        """Use a fake that answers."""
        # unittest.Mock works great with a completely fake object
        mock = Mock()
        mock.redirect_without_nonce = MagicMock(
            return_value='https://discourse_redirect'
        )
        mock.redirect = MagicMock()
        mock.sso_sync = MagicMock()
        self.use(mock)

    def down(self):
        """Use a client whose calls fail."""
        # unittest.Mock wants a concrete object to throw correctly
        mock = APIDiscourseClient(self.settings)
        mock.redirect_without_nonce = MagicMock(
            return_value='https://discourse_redirect', side_effect=Exception
        )
        mock.redirect = MagicMock(side_effect=Exception)
        mock.sso_sync = MagicMock(side_effect=Exception)
        self.use(mock)

    def restore(self):
        """Use the real client again."""
        self.use(self.original)
