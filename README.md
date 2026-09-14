# wFirma MCP

**Your accounting, one conversation away.**

Connect [wFirma](https://wfirma.pl) to **Claude, Codex, or any MCP client**. Ask about invoices, expenses, contractors, and declarations in plain language. Your assistant reads the records directly, so you can skip the exports and copy-paste.

- **Nine accounting tools** covering invoices, expenses, PIT/VAT/JPK/ZUS declarations, and revenue/VAT registers.
- **Read-only accounting access** — records stay unchanged; login and filters can update session or saved-view settings.
- **Runs on your computer** with your wFirma login. macOS Keychain support keeps credentials out of config files.

## Try asking

> Show my invoices for last month. Separate drafts and tell me if more pages are available.

> Open this invoice and show its line items, VAT breakdown, and contractor details.

> Pokaż ewidencję przychodów za ostatni miesiąc, z podziałem na stawki ryczałtu.

## Quick start

Requires **Python 3.11+**, [uv](https://docs.astral.sh/uv/getting-started/installation/), Git, and a wFirma account with password login. Supports macOS, Linux, and Windows.

### 1. Install

```sh
git clone https://github.com/tajchert/wfirma-mcp.git
cd wfirma-mcp
uv sync --locked
```

This Python server uses `uv`. The commands below launch the installed executable directly, so your assistant needs no package manager on its PATH.

### 2. Add your login

**macOS — save it to Keychain once:**

```sh
uv run --locked wfirma-mcp --setup-keychain
```

Enter your wFirma login and password in your terminal. The password is masked; allow Keychain access if macOS asks.

<details>
<summary>Linux, Windows, or a credentials file</summary>

Copy `.env.example` to `.env` and fill in `WFIRMA_LOGIN` and `WFIRMA_PASSWORD` locally. On macOS/Linux, run `chmod 600 .env`. On Windows, restrict access through the file's Security settings.

Append `--env-file /absolute/path/to/wfirma-mcp/.env` to the client commands below. For Claude Desktop, replace `"args": []` with:

```json
"args": ["--env-file", "/absolute/path/to/wfirma-mcp/.env"]
```

The file contains plaintext credentials; keep it private. `.env` is never loaded automatically. A saved macOS Keychain entry takes precedence; add `--credential-source plain` to bypass it. [More credential options](docs/reference.md#credential-precedence-and-fallbacks).

</details>

### 3. Connect your assistant

Replace `/absolute/path/to/wfirma-mcp` with your checkout's full path. On Windows, use `C:\path\to\wfirma-mcp\.venv\Scripts\wfirma-mcp.exe`; double the backslashes inside JSON strings.

#### Codex

```sh
codex mcp add wfirma -- "/absolute/path/to/wfirma-mcp/.venv/bin/wfirma-mcp"
```

Restart or reconnect Codex after registration. [Codex MCP guide](https://developers.openai.com/codex/mcp).

#### Claude Code

```sh
claude mcp add --transport stdio --scope user wfirma -- "/absolute/path/to/wfirma-mcp/.venv/bin/wfirma-mcp"
```

Run `/mcp` in Claude Code to check the connection. [Claude Code MCP guide](https://code.claude.com/docs/en/mcp).

#### Claude Desktop

Open **Settings → Developer → Edit Config** and add the `wfirma` entry to `claude_desktop_config.json`. Keep any existing servers.

```json
{
  "mcpServers": {
    "wfirma": {
      "command": "/absolute/path/to/wfirma-mcp/.venv/bin/wfirma-mcp",
      "args": []
    }
  }
}
```

Save, fully quit, and reopen Claude Desktop. [Desktop setup guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers).

**First message:** “Use wFirma to check my active company, then show last month's invoices.” Your assistant starts the server automatically. Keep the checkout at its configured path.

## What to know

- Uses wFirma's browser interface; no official API key is needed. Browser changes may affect compatibility. MFA/CAPTCHA are not supported yet.
- Lists return the **current page** and report whether more records exist. Saved filters can narrow results; ask your assistant to check the period and completeness before summarizing.
- Supports reading records. Invoice creation, payments, declaration submission, PDFs, company switching, and tax calculations are not available.
- Credentials stay local; session cookies stay in memory. **Retrieved accounting data is shared with your connected assistant.** [Privacy details](docs/privacy-and-protocol-audit.md).

## Reference & development

[All tools and advanced setup](docs/reference.md) · [Browser interface](WFIRMA_API.md) · [MIT license](LICENSE)

```sh
uv run pytest -q
uv run ruff check src tests scripts
```
