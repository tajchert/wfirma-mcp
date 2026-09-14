import json
import os
import sys

import pytest
from mcp import Client, StdioServerParameters
from test_client import client, scenario

from wfirma_mcp.client import Settings
from wfirma_mcp.server import create_server


async def test_mcp_tool_returns_structured_accounting_rows():
    handler, _ = scenario()
    async with client(handler) as api:
        server = create_server(client=api)
        response = await server.call_tool("list_invoices", {"year": 2031, "month": 7})
    result = response.structured_content
    assert result["company_id"] == "company-demo"
    assert result["rows"][0]["type"] == "normal_draft"
    assert result["complete"] is False
    assert "secret" not in str(response.content)


@pytest.mark.parametrize(
    "mode, expected_version", [("auto", "2026-07-28"), ("legacy", "2025-11-25")]
)
async def test_real_stdio_discovery_and_missing_credentials_are_safe(mode, expected_version):
    env = {key: value for key, value in os.environ.items() if not key.startswith("WFIRMA_")}
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "wfirma_mcp", "--credential-source", "plain"], env=env
    )
    async with Client(params, mode=mode) as session:
        assert session.protocol_version == expected_version
        tools = (await session.list_tools()).tools
        assert {t.name for t in tools} >= {
            "session_status",
            "list_invoices",
            "get_invoice",
            "get_vat_register",
            "get_contractor",
            "get_declaration",
        }
        assert all(t.annotations.read_only_hint for t in tools)
        response = await session.call_tool("session_status", {})
        assert response.is_error
        assert "WFIRMA_LOGIN" in response.content[0].text
        resources = await session.read_resource("wfirma://capabilities")
        capabilities = json.loads(resources.contents[0].text)
        assert capabilities["accounting_writes"] is False
        assert capabilities["pagination"] == "current_page_only"


def test_credentials_are_not_in_settings_representation():
    assert "private-password" not in repr(Settings("login", "private-password"))


async def test_tool_schemas_describe_records_and_input_bounds():
    server = create_server(Settings())
    tools = {tool.name: tool for tool in await server.list_tools()}
    invoices = tools["list_invoices"]
    assert {"rows", "pagination", "complete", "period", "company_id"} <= set(
        invoices.output_schema["properties"]
    )
    month = invoices.input_schema["properties"]["month"]["anyOf"][0]
    assert month["minimum"] == 1 and month["maximum"] == 12
    assert (
        tools["get_invoice"].input_schema["properties"]["invoice_id"]["pattern"]
        == "^[A-Za-z0-9_-]+$"
    )
    assert list(tools) == sorted(tools)


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_successful_accounting_result_through_stdio(mode):
    from pathlib import Path

    params = StdioServerParameters(
        command=sys.executable, args=[str(Path(__file__).with_name("stdio_fixture_server.py"))]
    )
    async with Client(params, mode=mode) as session:
        response = await session.call_tool("list_invoices", {"year": 2031, "month": 7})
    assert not response.is_error
    result = response.structured_content
    assert result["company_id"] == "company-demo"
    assert result["complete"] is False
    assert result["rows"][0]["cells"]["Invoice.total_composed"]["value"] == "1234.123456"
    assert "secret" not in str(response)
