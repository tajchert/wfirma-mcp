"""Serve real MCP tools against a synthetic HTTP boundary for subprocess tests."""

from test_client import client, scenario

from wfirma_mcp.server import create_server

if __name__ == "__main__":
    handler, _ = scenario()
    create_server(client=client(handler)).run(transport="stdio")
