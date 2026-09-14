"""Explicit opt-in live smoke check; prints no credentials, identifiers, or financial records."""

import argparse
import asyncio

from wfirma_mcp.client import Settings, WFirmaClient


async def run(env_file, year=None, month=None):
    async with WFirmaClient(Settings.load(env_file)) as client:
        await client.status()
        print("Live login and dashboard context: OK")
        result = await client.list_invoices(year=year, month=month)
        assert result["pagination"] and isinstance(result["rows"], list)
        print("Live invoice page and metadata: OK")
        if result["rows"]:
            await client.invoice_detail(result["rows"][0]["id"])
            print("Live invoice detail: OK")
        else:
            print("Live invoice detail: skipped (current view is empty)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--year", type=int)
    parser.add_argument("--month", type=int)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.env_file, args.year, args.month))
    except Exception as error:  # noqa: BLE001 - never print account data in a smoke-check traceback
        print(f"Live smoke check failed: {type(error).__name__}")
        raise SystemExit(1) from None
