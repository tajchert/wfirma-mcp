# Privacy and MCP protocol audit

Audit date: 14 September 2026. Package version: 0.2.0. MCP SDK: 2.2.0.

## Credential update — 15 September 2026, version 0.3.0

The current credential behavior supersedes the dotenv-only description in the historical audit below. macOS prefers a native Keychain item holding the login/password pair. If absent or unavailable, automatic mode reads explicit command-line credentials, environment variables, then an explicitly selected dotenv file. Linux and Windows use those portable sources without importing the macOS-only dependency. Strict Keychain and explicit portable modes are also available.

Setup uses a masked password prompt and does not write a plaintext fallback. Native credential-store errors and command-line parsing failures omit argument values. Dotenv files retain Unix permission checks on macOS/Linux; Windows uses ACLs, which users must configure themselves and which this implementation does not validate. See the [setup instructions](../README.md#credential-precedence-and-fallbacks).

Tests isolate the real Keychain and use synthetic credentials. Platform branches are simulated locally; the included CI workflow is configured for native macOS, Linux and Windows with Python 3.11 and 3.14. Native Linux/Windows CI execution and a real Keychain prompt were not exercised in this local session. No existing credentials were migrated or removed.

## Privacy findings

No embedded real credentials or account identifiers were found in the inspected implementation, synthetic tests, scripts, documentation, example environment file or dependency lockfile. An independent static review reached the same result. A local exact-value check also found no matches for the configured login or password in those files; it did not print their values. Test credentials, tax-ID-like strings, record IDs and company names are synthetic. Public examples use placeholders or explicitly synthetic values.

This is a scoped code/package audit, not a claim that the entire workspace or tool output contains no personal data:

- `.env` contains real credentials. Any HARs, `.private/` snapshots, bank exports or generated reports must remain private and are excluded from release packages.
- Root CSV/TSV bank exports were previously unignored. They are now ignored so a normal `git add .` cannot accidentally include them. Package inclusion is additionally controlled by an independent explicit allowlist.
- When used, tools intentionally return private accounting records to the connected MCP client, potentially including names, addresses, tax IDs, bank-account details, document IDs and financial amounts. The server does not anonymize records or control the host's retention of returned data.
- Credentials are never tool arguments. The credentials file must be explicitly selected and owner-only; no implicit dotenv lookup occurs. Cookies and AJAX tokens remain in memory. The only external application destination is `https://wfirma.pl`, and this launcher exposes no network listener.
- Tool input validation errors and unexpected output-validation errors omit the supplied values. Explicit output models reject unexpected fields, including accidentally added credential/token fields.
- There is no telemetry exporter dependency or exporter configuration. SDK 2.2 depends on the OpenTelemetry API, whose spans have no collector without an explicitly installed/configured exporter. The SDK implementation was inspected; normal trace attributes describe protocol method/version and tool identity, not accounting arguments/results. No telemetry backend was added.

Heuristic review cannot establish the absence of every possible identifier. The exact credential check covered locally configured values, not every historical account value. Account-specific observations in the API reference and supporting documentation have been generalized, and reused capture periods/counts in examples have been replaced with synthetic values. Review additions before public release and rerun archive checks after building.

## Protocol changes addressed

The [July 2026 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog) and [official SDK migration guide](https://py.sdk.modelcontextprotocol.io/migration/) informed this upgrade.

| Change | This server |
| --- | --- |
| Discovery and request metadata | SDK 2.2; raw stdio tests call `server/discover` and tools without initialization |
| Result discrimination and server identity | Tests verify `resultType`, server name and package version |
| Unsupported versions | Wire test verifies error `-32022` |
| Cacheable results | Private scope and five-minute freshness for static metadata/capability resources |
| Deterministic discovery | Tools sorted by name and compared across repeated requests |
| JSON Schema support | Explicit Pydantic input/output schemas, decimal strings and response validation |
| Compatibility | Modern and legacy SDK clients plus raw legacy requests without modern metadata |
| HTTP sessions/headers, OAuth, subscriptions, MRTR and task extensions | No remote HTTP endpoint, OAuth flow, subscriptions, elicitation or background-task features added |

The local wFirma cookie jar is an application authentication cache for one configured user. It is independent of MCP protocol sessions. Tools and resources never change per connection. The server is intended for a local single-user stdio process; sharing it as a multi-user HTTP service would require a separate authorization and account-isolation design.

## Verification

- All 50 automated tests pass. They cover parser contracts, credentials, company/period checking, privacy regressions and both MCP protocol eras, including successful accounting-result transmission over subprocess stdio using synthetic records. Ruff and package builds pass.
- Output models were validated locally against saved responses without publishing their records, periods, counts or amounts.
- Wheel and source archives are inspected for forbidden private filenames and embedded configured credentials before delivery.
- The registered Codex executable path stays unchanged. Reconnect the MCP server or start a new task to load version 0.2.0.

This establishes tested support for the applicable local-server features, not certification of every optional MCP feature. Existing business limitations remain: browser-interface dependence, current-page-only accounting lists, unimplemented MFA/company switching, and no accounting writes.
