"""Keep automated tests away from the user's real credential store."""

import pytest

from wfirma_mcp import credentials


@pytest.fixture(autouse=True)
def isolate_keychain(monkeypatch):
    def unavailable():
        raise RuntimeError("Native Keychain is disabled in tests")

    monkeypatch.setattr(credentials, "_macos_keyring", unavailable)
