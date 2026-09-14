"""Privacy regressions use synthetic data only, never the real credentials file."""

import subprocess
import sys

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_client import client, scenario

from wfirma_mcp.client import Settings, WFirmaError
from wfirma_mcp.server import create_server


def test_private_exports_and_credentials_are_ignored_by_git():
    paths = [
        "synthetic-bank.csv",
        "synthetic-ledger.tsv",
        ".env",
        ".private/example.html",
        "example.har",
    ]
    result = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        input="\n".join(paths),
        text=True,
        capture_output=True,
        check=True,
    )
    assert set(result.stdout.splitlines()) == set(paths)


def test_credentials_require_explicit_file_and_environment_overrides_it(tmp_path, monkeypatch):
    for key in ("WFIRMA_LOGIN", "WFIRMA_PASSWORD", "WFIRMA_COMPANY_ID"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text("WFIRMA_LOGIN=synthetic@example.invalid\nWFIRMA_PASSWORD=synthetic-local\n")
    path.chmod(0o600)
    monkeypatch.chdir(tmp_path)
    assert Settings.load().login == ""
    assert Settings.load().password == ""
    monkeypatch.setenv("WFIRMA_PASSWORD", "synthetic-override")
    settings = Settings.load(str(path))
    assert settings.login == "synthetic@example.invalid"
    assert settings.password == "synthetic-override"
    assert "synthetic" not in repr(settings)
    if sys.platform != "win32":
        path.chmod(0o644)
        with pytest.raises(WFirmaError):
            Settings.load(str(path))


async def test_unexpected_secret_fields_are_rejected_by_output_validation(monkeypatch):
    handler, _ = scenario()
    async with client(handler) as api:

        async def unexpected_status():
            return {
                "authenticated": True,
                "company_id": "synthetic-company",
                "company_pinned": True,
                "accounting_access": "read-only",
                "token": "synthetic-secret-must-not-leak",
            }

        monkeypatch.setattr(api, "status", unexpected_status)
        server = create_server(client=api)
        with pytest.raises(ToolError) as error:
            await server.call_tool("session_status", {})
        assert "synthetic-secret" not in str(error.value)
