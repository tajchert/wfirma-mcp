# wFirma MCP design

Implement a local stdio MCP server, using the MCP Python SDK 2.2 line (upgraded in version 0.2.0), HTTPX for cookie-aware HTTP, and Beautiful Soup for HTML. Credentials come from environment variables or an explicitly selected dotenv file. The user's request authorizes implementation and local setup.

The source is the documented browser interface, not wFirma's official API. Expose only documented accounting reads: session status, invoice month/range lists and details, expenses/drafts, contractor details, PIT/JPK/VAT/ZUS declarations and details, revenue month register, VAT registers. Preserve decimal strings, localized display values, drafts, active filters, and metadata. Paginated lists return the current page with explicit completeness; unvalidated paging/search/sort and company switching are not exposed. No arbitrary URL tool, accounting writes, logout, or forecast refresh.

A session owns cookies, tokens and a lock. Every operation serializes page navigation plus dependent AJAX requests. All network destinations and redirects are restricted to https://wfirma.pl. Login form actions must point to /logowanie. Verify company context on full pages and optionally pin it with WFIRMA_COMPANY_ID. Fail closed on missing context, login pages, unexpected tables, invalid periods and HTTP failures; never retry a password or form POST automatically. Authentication stays in memory and error messages omit response bodies, passwords, cookies and tokens.

HTML parsing is separate from transport and MCP tools. Data tables map exact localized labels to semantic columns; detail tables stay separate. JPK XML uses defusedxml and reports its actual namespace. No live financial records or HAR data are used as committed test fixtures.

Verification: synthetic parser fixtures, HTTPX mock transport tests for auth/cookies/tokens/redirects/periods, and a real MCP stdio client handshake/tool invocation. A minimal live read may verify local credentials and company context without printing private data. Package lock and Codex registration make this reusable in later tasks.

Version 0.2.0 adds modern discovery/per-request protocol support through SDK 2.2, tested legacy compatibility, private metadata cache hints, explicit validated output models, constrained input schemas, deterministic tool ordering and redaction of SDK validation errors. See privacy-and-protocol-audit.md.
