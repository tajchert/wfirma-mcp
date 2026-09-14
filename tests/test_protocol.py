"""Exercise actual JSON-RPC on stdio, independently of SDK client negotiation."""

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager

import pytest

VERSION = "2026-07-28"
META = {
    "io.modelcontextprotocol/protocolVersion": VERSION,
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "synthetic-test-client", "version": "1"},
}


@asynccontextmanager
async def wire_server():
    env = {k: v for k, v in os.environ.items() if not k.startswith("WFIRMA_")}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "wfirma_mcp",
        "--credential-source",
        "plain",
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    sequence = 0

    async def request(method, params=None):
        nonlocal sequence
        sequence += 1
        message = {"jsonrpc": "2.0", "id": sequence, "method": method, "params": params or {}}
        process.stdin.write(json.dumps(message).encode() + b"\n")
        await process.stdin.drain()
        for _ in range(20):
            line = await asyncio.wait_for(process.stdout.readline(), timeout=10)
            assert line, "Server terminated without a protocol result"
            response = json.loads(line)
            if response.get("id") == sequence:
                return response
        pytest.fail("No response for the request")

    async def notify(method):
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}).encode() + b"\n")
        await process.stdin.drain()

    request.notify = notify
    try:
        yield request
    finally:
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()


async def test_modern_discovery_without_initialize_has_identity_and_versions():
    async with wire_server() as request:
        reply = await request("server/discover", {"_meta": META})
    assert "error" not in reply
    result = reply["result"]
    assert VERSION in result["supportedVersions"]
    assert result["resultType"] == "complete"
    info = result["_meta"]["io.modelcontextprotocol/serverInfo"]
    assert info["name"] == "wFirma"
    assert info["version"]


async def test_modern_requests_work_without_any_handshake_with_private_cache_hints():
    async with wire_server() as request:
        first = await request("tools/list", {"_meta": META})
        second = await request("tools/list", {"_meta": META})
        resource = await request("resources/read", {"uri": "wfirma://capabilities", "_meta": META})
        error = await request(
            "tools/call", {"name": "session_status", "arguments": {}, "_meta": META}
        )
    assert "error" not in first
    assert first["result"]["tools"] == second["result"]["tools"]
    for reply in (first, resource):
        result = reply["result"]
        assert result["resultType"] == "complete"
        assert result["cacheScope"] == "private"
        assert result["ttlMs"] >= 0
        assert "io.modelcontextprotocol/serverInfo" in result["_meta"]
    assert error["result"]["resultType"] == "complete"
    assert error["result"]["isError"] is True


async def test_unsupported_protocol_returns_standard_error():
    async with wire_server() as request:
        reply = await request(
            "tools/list",
            {"_meta": {**META, "io.modelcontextprotocol/protocolVersion": "2099-01-01"}},
        )
    assert reply["error"]["code"] == -32022


async def test_invalid_arguments_do_not_echo_sensitive_client_input():
    marker = "synthetic-private-input-do-not-echo"
    async with wire_server() as request:
        reply = await request(
            "tools/call",
            {"name": "list_invoices", "arguments": {"year": marker, "month": 7}, "_meta": META},
        )
    assert reply["result"]["isError"] is True
    assert marker not in json.dumps(reply)


async def test_legacy_client_without_modern_metadata_still_works():
    async with wire_server() as request:
        initialized = await request(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "synthetic-legacy-client", "version": "1"},
            },
        )
        assert initialized["result"]["protocolVersion"] == "2025-11-25"
        await request.notify("notifications/initialized")
        tools = await request("tools/list")
        response = await request("tools/call", {"name": "session_status", "arguments": {}})
    assert len(tools["result"]["tools"]) == 9
    assert response["result"]["isError"] is True
