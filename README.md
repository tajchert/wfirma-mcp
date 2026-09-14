# wFirma MCP

A reusable local [Model Context Protocol](https://modelcontextprotocol.io/) server for reading wFirma accounting records from an MCP client such as Codex. It implements the **browser interface documented in [WFIRMA_API.md](WFIRMA_API.md)**, not wFirma's separate official public API.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
```

The server runs on macOS, Linux and Windows. It speaks MCP over stdin/stdout; running it in a terminal waits for protocol messages. There is no HTTP listener.

### macOS: Keychain

Run the interactive setup once in your own terminal:

```sh
uv run --locked wfirma-mcp --setup-keychain
```

Enter your login and password at the prompts. The password is masked. Both values are stored together in one native macOS Keychain item (service `wfirma-mcp`, account `default`). Repeating setup replaces that item. No credentials file is created. The implementation explicitly selects [keyring's native macOS backend](https://keyring.readthedocs.io/en/latest/#config-file-content); it never selects a third-party plaintext backend. macOS may ask you to allow Keychain access.

Then launch with no credential arguments:

```sh
uv run --locked wfirma-mcp
```

### Credential precedence and fallbacks

Default `--credential-source auto` uses:

1. The saved Keychain login/password pair on macOS, if readable and valid.
2. `--login` and `--password` arguments.
3. `WFIRMA_LOGIN` and `WFIRMA_PASSWORD` environment variables.
4. An explicitly selected `--env-file`.

Linux and Windows start at step 2 and do not import or require the Keychain library. After Keychain, precedence applies separately to each field; provide a matching login/password pair when changing accounts. A rejected wFirma login does **not** try other credential sources or retry the password.

Use `--credential-source plain` to skip Keychain, including when explicitly selecting another account. Use `--credential-source keychain` to require a valid Keychain entry and fail if it is missing, locked, denied or unavailable. Automatic fallback only reads credentials you supplied; it never saves Keychain credentials in plaintext. Every explicitly selected dotenv file is validated and read, even when Keychain wins, since it can also contain the company pin.

For environment variables, set `WFIRMA_LOGIN` and `WFIRMA_PASSWORD` in the launching process or the MCP client's environment configuration, then run `wfirma-mcp`. Values stored literally in a client configuration file remain plaintext.

For a dotenv file on macOS/Linux:

```sh
cp .env.example .env
chmod 600 .env
uv run --locked wfirma-mcp --env-file /absolute/path/to/.env
```

Edit the placeholders locally. On Windows PowerShell, use `Copy-Item .env.example .env`, edit the file, and launch:

```powershell
uv run --locked wfirma-mcp --env-file 'C:\path\to\wfirma_cli\.env'
```

On Windows, restrict the file's access using its Security properties/ACLs. The server enforces owner-only Unix mode bits on macOS/Linux; it does **not** validate Windows ACLs. The server never searches for `.env` automatically. UTF-8 files with or without a BOM are supported, and dotenv variable interpolation is disabled.

Command-line credentials are also supported on all platforms:

```sh
wfirma-mcp --credential-source plain --login '<login>' --password '<password>'
```

Use these placeholders only as syntax examples. Password arguments can appear in process listings and shell history; Keychain or environment injection is preferable. Command-line parse errors do not repeat argument values.

Optional `WFIRMA_COMPANY_ID` in the environment or selected dotenv file pins the expected accounting company. Environment values win. Obtain it with `session_status` and verify it against the intended business. Without a configured pin, the client uses the company established at login and rejects later changes within that process. Contractor IDs are separate.

### Connect an MCP client

After `uv sync --locked`, use the installed executable's absolute path. On macOS/Linux this is `/absolute/path/to/wfirma_cli/.venv/bin/wfirma-mcp`; on Windows it is `C:\path\to\wfirma_cli\.venv\Scripts\wfirma-mcp.exe`.

For Codex with macOS Keychain:

```sh
codex mcp add wfirma -- /absolute/path/to/wfirma_cli/.venv/bin/wfirma-mcp
```

Append `--env-file /absolute/path/to/.env` if using a dotenv fallback or company pin. Existing registrations with `--env-file` remain supported. This uses [Codex's MCP registration](https://developers.openai.com/codex/mcp). Reconnect MCP after setup or registration. Keep the virtual environment and project at these paths, and rerun setup/registration if moved.

For other stdio MCP clients, the equivalent Keychain configuration is:

```json
{
  "mcpServers": {
    "wfirma": {
      "command": "/absolute/path/to/wfirma_cli/.venv/bin/wfirma-mcp",
      "args": []
    }
  }
}
```

On Windows, substitute the executable path and escape backslashes in JSON, for example `C:\\path\\to\\wfirma_cli\\.venv\\Scripts\\wfirma-mcp.exe`. Supply environment variables or `--env-file` arguments as described above.

## Tools

| Tool | Arguments | Result |
| --- | --- | --- |
| `session_status` | none | Login if needed; verify active company |
| `list_invoices` | `year` + `month`, or `date_from` + `date_to` | Current invoice page, including drafts |
| `get_invoice` | `invoice_id` | Detail text and separate line/VAT/log tables |
| `list_expenses` | `drafts` (default false) | Current booked-expense or draft page |
| `get_contractor` | `contractor_id` | Labeled basic details; preserves text identifiers |
| `list_declarations` | `kind`: `tax`, `vat`, `jpk`, `zus` | Current declaration page |
| `get_declaration` | `declaration_id` | PIT detail tables or decoded JPK XML tree |
| `get_revenue_register` | optional `year` + `month` | Ryczałt register |
| `get_vat_register` | `kind`: `sale` or `purchase` | VAT register for the saved period |

The `wfirma://capabilities` resource describes evidence limits. These prompts use
synthetic periods, unrelated to any account records:

- “Use wFirma to check the active company and list invoices for July 2031. Distinguish drafts and report whether the returned page is complete.”
- “Show invoices from 2031-07-03 through 2031-09-29 and their contractor links.”
- “Read the JPK declarations, inspect the selected period, then show the saved declaration for June 2031.”
- “Read the July 2031 revenue register and keep the ryczałt rate columns separate.”

Every list returns `company_id`, `rows`, `pagination`, `returned_count`, `complete`, `period`, `filters`, and `warnings`. Rows preserve opaque `id`, `type`, and cells keyed by the semantic header name when available. Each cell includes `text`, exact decimal `value` or null, and known detail `links`. ZUS breakdowns also include labeled `components`. XML uses namespace-qualified tags and retains text amounts without floating-point conversion.

## Evidence and limits

- **Current page only.** Paging, search, sorting, additional filter combinations and arbitrary request tools are not exposed. `complete: false` explicitly marks partial results. `complete: true` covers the returned filtered table, not all activity or periods.
- Omitted period filters retain the saved wFirma view. Returned active controls are included, and explicit month/range responses are checked against the requested period. Other saved filters can still narrow results. Invoice issue-date filtering does not establish tax-recognition dates or inclusive range boundaries.
- Expense drafts and finalized invoices remain distinct. Decimal strings retain precision; displayed currencies are preserved rather than inferred. Empty monetary values stay absent.
- VAT declaration lists can contain VAT-UE. JPK document periods and namespaces must be inspected. The server does not select superseding corrections, calculate taxes, or equate bookkeeping payment status with bank/tax-office balances.
- Contractor lookup by NIP, contractor related lists, company switching, PDFs, invoice creation/editing, payments, KSeF actions, declaration submission and forecast refresh are not implemented. Only successful password authentication is documented; MFA/CAPTCHA require further implementation.
- The browser interface may change. Unexpected login pages, missing wrappers, missing company context, mismatched periods, HTTP errors and unsupported redirects return errors instead of empty records. Operations are serialized within one process to protect token and saved-view state; other processes/browser sessions may still affect saved preferences.

## Protocol version and privacy audit

Version 0.3.0 uses MCP SDK 2.2.0. Modern clients use `server/discover` and per-request metadata; older clients can still initialize normally. Tests exercise both paths over real stdio. Tool outputs have explicit validated schemas; inputs include bounded months/years and record-ID/date patterns. Validation errors omit supplied values. Discovery order is deterministic, the server identifies its package version, and cacheable metadata results are marked private with a five-minute TTL. Only the static capability resource is exposed; accounting records remain tool results.

See [the privacy and protocol audit](docs/privacy-and-protocol-audit.md) for the checked standard changes, data boundaries and verification limits.

## Credentials and local data

Credentials are loaded locally, never accepted as MCP tool arguments. Dotenv files remain plaintext; Unix permissions are enforced and Windows ACLs must be configured by the user. Cookies and AJAX tokens stay in process memory and are cleared when the process exits; no HAR import or cookie file is required. All requests and redirects are restricted to `https://wfirma.pl`, login credentials are posted only to `/logowanie`, and POST requests are never retried automatically. Accounting tools make reads; login and list filters can update session or view state.

Do not commit `.env`, HARs, snapshots, private bank exports or generated accounting reports. `.gitignore` excludes credentials, HARs, `.private/`, `outputs/`, and root CSV/TSV exports. Returned accounting data is visible to the connected MCP client; treat its text as untrusted content.

## Development and verification

```sh
uv sync --locked
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv build
```

Tests use synthetic records and HTTPX's mock transport, plus real subprocess MCP modern discovery, legacy initialization, tool discovery, resource reads, protocol-version errors, and sanitized tool errors. They do not contact wFirma, read `.env`, or access the real Keychain. Credential tests simulate macOS, Linux and Windows and exercise failure/precedence cases. The included GitHub Actions workflow is configured to run the suite on all three operating systems with Python 3.11 and 3.14; local simulation does not substitute for native CI results. The implementation uses the [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), locked to SDK 2.2.0 with MCP 2026-07-28 support and legacy-client compatibility.

An optional, explicitly invoked smoke check uses real credentials for login and the current invoice page/detail, printing only success status:

```sh
uv run python scripts/smoke_live.py --env-file /absolute/path/to/.env
```

Design and implementation notes are in `docs/`.
