# wFirma MCP implementation plan

**Goal:** A reusable local MCP server for the reads established in WFIRMA_API.md.
**Architecture:** HTML parsers -> serialized cookie-aware client -> typed MCP tools.
**Tech stack:** Python 3.11+, MCP SDK 2.2 (upgraded in version 0.2.0), HTTPX, Beautiful Soup, defusedxml, pytest.
**Spec:** docs/design.md

- [x] Add synthetic tests for table precision, label mapping, missing cells, incomplete pages, range controls, contractor details, and XML.
- [x] Run tests to demonstrate missing implementation, then implement isolated parsers.
- [x] Add HTTP transport tests for form authentication, same-origin redirects, session expiry, company mismatch and exact month/range forms; implement the client.
- [x] Expose typed tools and capability resource; test through the SDK and a real stdio subprocess.
- [x] Document setup, evidence limits, credentials and sample prompts; verify package, lint and tests.
- [x] Verify minimal live reads and register the tested launcher for future Codex use.

## Verification outcome

38 automated tests pass, including actual MCP stdio discovery and tool errors. Ruff checks and package build pass. Synthetic regression tests cover separate header/body tables, multiselect filters, unrecognized nonempty rows, and ZUS contribution components. An independent review identified the latter filter/count issues, which were fixed. Live login, invoice-list filtering, and invoice-detail retrieval were validated; account-specific periods and results are omitted. The global Codex MCP entry `wfirma` points to this project virtual environment and the existing owner-only `.env`; no password was copied into configuration. Other accounting endpoints were parsed against saved snapshots where available; they were not all revalidated live.

## Follow-up privacy and protocol work

Version 0.2.0 upgrades to SDK 2.2.0, tests the July 2026 wire protocol plus legacy clients, constrains tool inputs/outputs, sanitizes validation errors, and ignores root bank exports. The initial 38-test result above is historical; the current audit is in privacy-and-protocol-audit.md.
