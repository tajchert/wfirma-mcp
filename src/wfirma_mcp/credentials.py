"""Local credentials: macOS Keychain, then explicitly supplied portable sources."""

import getpass
import json
import os
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

SERVICE = "wfirma-mcp"
ACCOUNT = "default"


class WFirmaError(ValueError):
    """A safe-to-display error, without upstream bodies or credentials."""


def _macos_keyring():
    # Select the native backend explicitly: never load third-party plaintext stores.
    from keyring.backends.macOS import Keyring

    return Keyring()


def _read_keychain(*, required: bool):
    if sys.platform != "darwin":
        if required:
            raise WFirmaError("Keychain is only supported on macOS; use portable credentials.")
        return None
    try:
        value = _macos_keyring().get_password(SERVICE, ACCOUNT)
        if value is not None:
            entry = json.loads(value)
            if (
                isinstance(entry, dict)
                and isinstance(entry.get("login"), str)
                and entry["login"]
                and isinstance(entry.get("password"), str)
                and entry["password"]
            ):
                return entry["login"], entry["password"]
    except Exception:  # noqa: BLE001 - sanitize all native/import errors at this boundary
        # Native backend errors can include account names and private details.
        if required:
            raise WFirmaError("Cannot read macOS Keychain credentials.") from None
        return None
    if required:
        raise WFirmaError("No valid Keychain credentials; run wfirma-mcp --setup-keychain.")
    return None


def save_keychain(login: str, password: str):
    """Store the pair in one native Keychain item; never write a plaintext fallback."""
    if sys.platform != "darwin":
        raise WFirmaError("Keychain setup is only supported on macOS.")
    if not login or not password:
        raise WFirmaError("Login and password must both be nonempty.")
    try:
        _macos_keyring().set_password(
            SERVICE, ACCOUNT, json.dumps({"login": login, "password": password})
        )
    except Exception:  # noqa: BLE001 - never expose native credential-store error details
        raise WFirmaError(
            "Cannot save macOS Keychain credentials; nothing was saved to a file."
        ) from None


def setup_keychain():
    """Interactive setup is separate from the MCP stdio lifecycle."""
    if sys.platform != "darwin":
        raise WFirmaError("Keychain setup is only supported on macOS.")
    try:
        login = input("wFirma login: ").strip()
        with warnings.catch_warnings():
            # getpass otherwise falls back to an echoing prompt without a terminal.
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("wFirma password: ")
    except (EOFError, KeyboardInterrupt, OSError, getpass.GetPassWarning):
        raise WFirmaError("Keychain setup cancelled; use an interactive terminal.") from None
    save_keychain(login, password)
    print("Credentials saved in macOS Keychain.", file=sys.stderr)


@dataclass(frozen=True)
class Settings:
    login: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    company_id: str | None = None

    @classmethod
    def load(
        cls,
        env_file: str | None = None,
        *,
        login: str | None = None,
        password: str | None = None,
        credential_source: str = "auto",
    ):
        if credential_source not in {"auto", "keychain", "plain"}:
            raise WFirmaError("Invalid credential source; use auto, keychain or plain.")
        values = {}
        if env_file:
            path = Path(env_file).expanduser()
            try:
                if not path.is_file():
                    raise WFirmaError("Configured credentials file does not exist.")
                # Windows uses ACLs; its synthetic mode bits do not measure privacy.
                if sys.platform != "win32" and path.stat().st_mode & 0o077:
                    raise WFirmaError("Credentials file must be owner-only; run chmod 600 on it.")
                values.update(dotenv_values(path, interpolate=False, encoding="utf-8-sig"))
            except (OSError, UnicodeError):
                raise WFirmaError("Cannot read the configured credentials file.") from None
        values.update(os.environ)
        saved = None
        if credential_source != "plain":
            saved = _read_keychain(required=credential_source == "keychain")
        if saved is not None:
            resolved_login, resolved_password = saved
        else:
            resolved_login = login if login is not None else values.get("WFIRMA_LOGIN") or ""
            resolved_password = (
                password if password is not None else values.get("WFIRMA_PASSWORD") or ""
            )
        return cls(resolved_login, resolved_password, values.get("WFIRMA_COMPANY_ID") or None)
