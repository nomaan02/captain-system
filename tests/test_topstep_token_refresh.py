# region imports
from AlgorithmImports import *
# endregion
"""Unit tests for TopstepXClient.validate_token() — C1 fix verification.

Tests confirm:
1. Token refresh succeeds when API returns {"success": true, "newToken": "..."}
2. Missing newToken in a successful response raises AuthenticationError
3. Failed response (success=false, no newToken) raises AuthenticationError
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from shared.topstep_client import TopstepXClient, AuthenticationError


@pytest.fixture
def client():
    """Create a TopstepXClient with a dummy token already set."""
    c = TopstepXClient(username="test@example.com", api_key="fake-key")
    c._token = "old-jwt-token"
    c._token_acquired_at = 0.0
    return c


class TestValidateTokenC1:
    """C1: validate_token must read resp['newToken'], not resp['token']."""

    @patch.object(TopstepXClient, "_post")
    def test_refresh_success_updates_token(self, mock_post, client):
        """Normal refresh: API returns newToken, client stores it."""
        mock_post.return_value = {
            "success": True,
            "errorCode": 0,
            "errorMessage": None,
            "newToken": "refreshed-jwt-abc123",
        }

        result = client.validate_token()

        assert result == "refreshed-jwt-abc123"
        assert client._token == "refreshed-jwt-abc123"
        assert client._token_acquired_at > 0
        mock_post.assert_called_once_with("/Auth/validate", {}, skip_refresh=True)

    @patch.object(TopstepXClient, "_post")
    def test_refresh_missing_new_token_raises(self, mock_post, client):
        """success=True but newToken missing raises AuthenticationError."""
        mock_post.return_value = {
            "success": True,
            "errorCode": 0,
            "errorMessage": None,
            # newToken deliberately omitted
        }

        with pytest.raises(AuthenticationError, match="missing 'newToken' field"):
            client.validate_token()

        # Token should NOT have been updated
        assert client._token == "old-jwt-token"

    @patch.object(TopstepXClient, "_post")
    def test_refresh_failure_raises(self, mock_post, client):
        """success=False with no newToken raises AuthenticationError."""
        mock_post.return_value = {
            "success": False,
            "errorCode": "INVALID_TOKEN",
            "errorMessage": "Token expired",
        }

        with pytest.raises(AuthenticationError, match="Token validation failed"):
            client.validate_token()

        # Token should NOT have been updated
        assert client._token == "old-jwt-token"

    @patch.object(TopstepXClient, "_post")
    def test_refresh_does_not_read_token_field(self, mock_post, client):
        """Regression: even if resp has a 'token' field, newToken is used."""
        mock_post.return_value = {
            "success": True,
            "errorCode": 0,
            "token": "wrong-field-should-not-be-used",
            "newToken": "correct-new-token",
        }

        result = client.validate_token()

        assert result == "correct-new-token"
        assert client._token == "correct-new-token"
