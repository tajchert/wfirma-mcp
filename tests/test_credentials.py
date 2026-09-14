"""Credential resolution uses synthetic data and a fake OS store only."""

import json
import sys

import pytest

from wfirma_mcp.client import Settings, WFirmaError


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in ("WFIRMA_LOGIN", "WFIRMA_PASSWORD", "WFIRMA_COMPANY_ID"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_portable_argument_environment_precedence(platform, monkeypatch):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setenv("WFIRMA_LOGIN", "env-user")
    monkeypatch.setenv("WFIRMA_PASSWORD", "env-pass")
    settings = Settings.load(password="argument-pass")
    assert (settings.login, settings.password) == ("env-user", "argument-pass")


def test_argument_environment_and_file_precedence_on_native_filesystem(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("WFIRMA_LOGIN=file-user\nWFIRMA_PASSWORD=file-pass\n")
    path.chmod(0o600)
    monkeypatch.setenv("WFIRMA_LOGIN", "env-user")
    settings = Settings.load(str(path), password="argument-pass")
    assert (settings.login, settings.password) == ("env-user", "argument-pass")


class MemoryKeychain:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error

    def get_password(self, service, account):
        assert (service, account) == ("wfirma-mcp", "default")
        if self.error:
            raise self.error
        return self.value

    def set_password(self, service, account, value):
        assert (service, account) == ("wfirma-mcp", "default")
        if self.error:
            raise self.error
        self.value = value


def install_store(monkeypatch, store):
    from wfirma_mcp import credentials

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(credentials, "_macos_keyring", lambda: store)


def test_keychain_credentials_win_as_a_pair_and_company_pin_survives(monkeypatch):
    install_store(monkeypatch, MemoryKeychain(json.dumps({"login": "saved", "password": "secret"})))
    monkeypatch.setenv("WFIRMA_COMPANY_ID", "synthetic-company")
    settings = Settings.load(login="other", password="other-secret")
    assert (settings.login, settings.password) == ("saved", "secret")
    assert settings.company_id == "synthetic-company"
    assert "secret" not in repr(settings)


@pytest.mark.parametrize("value", [None, "not-json", "[]", '{"login":"only"}'])
def test_missing_or_invalid_keychain_entry_falls_back_without_writing(value, monkeypatch):
    store = MemoryKeychain(value)
    install_store(monkeypatch, store)
    settings = Settings.load(login="fallback", password="fallback-pass")
    assert (settings.login, settings.password) == ("fallback", "fallback-pass")
    assert store.value == value


def test_unavailable_keychain_falls_back_but_strict_mode_is_sanitized(monkeypatch):
    install_store(monkeypatch, MemoryKeychain(error=RuntimeError("synthetic-secret")))
    monkeypatch.setenv("WFIRMA_LOGIN", "fallback")
    monkeypatch.setenv("WFIRMA_PASSWORD", "fallback-pass")
    assert Settings.load().password == "fallback-pass"
    with pytest.raises(WFirmaError) as error:
        Settings.load(credential_source="keychain")
    assert "synthetic-secret" not in str(error.value)


def test_plain_mode_bypasses_saved_keychain(monkeypatch):
    install_store(monkeypatch, MemoryKeychain(json.dumps({"login": "saved", "password": "secret"})))
    settings = Settings.load(login="chosen", password="chosen-pass", credential_source="plain")
    assert (settings.login, settings.password) == ("chosen", "chosen-pass")


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_non_mac_does_not_import_keyring_and_strict_mode_fails(platform, monkeypatch):
    from wfirma_mcp import credentials

    monkeypatch.setattr(sys, "platform", platform)

    def unexpected():
        pytest.fail("Non-macOS credential loading touched Keychain")

    monkeypatch.setattr(credentials, "_macos_keyring", unexpected)
    assert Settings.load().password == ""
    with pytest.raises(WFirmaError):
        Settings.load(credential_source="keychain")


def test_windows_dotenv_does_not_use_unix_mode_bits(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    path = tmp_path / ".env"
    path.write_text("WFIRMA_LOGIN=file-user\nWFIRMA_PASSWORD=file-pass\n")
    path.chmod(0o666)
    assert Settings.load(str(path)).password == "file-pass"


def test_setup_round_trip_keeps_both_credentials_in_keychain(monkeypatch):
    from wfirma_mcp import credentials

    store = MemoryKeychain()
    install_store(monkeypatch, store)
    credentials.save_keychain("synthetic@example.invalid", "special-£-$-password")
    settings = Settings.load(credential_source="keychain")
    assert (settings.login, settings.password) == (
        "synthetic@example.invalid",
        "special-£-$-password",
    )


def test_setup_failure_never_creates_plaintext_file(tmp_path, monkeypatch):
    from wfirma_mcp import credentials

    monkeypatch.chdir(tmp_path)
    install_store(monkeypatch, MemoryKeychain(error=RuntimeError("synthetic-secret")))
    with pytest.raises(WFirmaError) as error:
        credentials.save_keychain("user", "synthetic-secret")
    assert "synthetic-secret" not in str(error.value)
    assert list(tmp_path.iterdir()) == []


def test_cli_setup_prompts_and_exits_without_starting_mcp(monkeypatch, capsys):
    from wfirma_mcp import credentials, server

    store = MemoryKeychain()
    install_store(monkeypatch, store)
    monkeypatch.setattr(sys, "argv", ["wfirma-mcp", "--setup-keychain"])
    monkeypatch.setattr("builtins.input", lambda prompt: "prompt-user")
    monkeypatch.setattr(credentials.getpass, "getpass", lambda prompt: "prompt-password")
    server.main()
    assert Settings.load().login == "prompt-user"
    output = capsys.readouterr()
    assert output.out == ""
    assert "prompt-password" not in output.err


def test_cli_passes_portable_credentials_to_server(monkeypatch):
    from wfirma_mcp import server

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "wfirma-mcp",
            "--credential-source",
            "plain",
            "--login",
            "arg-user",
            "--password",
            "arg-password",
        ],
    )
    observed = []

    class Server:
        def run(self, *, transport):
            assert transport == "stdio"

    def create(settings):
        observed.append(settings)
        return Server()

    monkeypatch.setattr(server, "create_server", create)
    server.main()
    assert (observed[0].login, observed[0].password) == ("arg-user", "arg-password")


def test_cli_parse_errors_do_not_echo_credentials(monkeypatch, capsys):
    from wfirma_mcp import server

    monkeypatch.setattr(
        sys, "argv", ["wfirma-mcp", "--password", "synthetic-secret", "accidental-secret-argument"]
    )
    with pytest.raises(SystemExit) as error:
        server.main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert "synthetic-secret" not in output.err
    assert "accidental-secret-argument" not in output.err
