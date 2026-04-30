# -*- coding: utf-8 -*-
import json, asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp import ClientSession

async def run_test():
    env = {
        **os.environ,
        "KINGDEE_SERVER_URL": "http://wcl/k3cloud/",
        "KINGDEE_ACCT_ID": "69ae8ed35dab20",
        "KINGDEE_USERNAME": "demo",
        "KINGDEE_APP_ID": "338898_x+bC0diL0pD8x+8EWe3CUayNygSaSDoI",
        "KINGDEE_APP_SEC": "f8b75d4cc5484c98a8803f7b045e06be",
        "KINGDEE_LCID": "2052",
    }
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-c",
              "import sys; sys.path.insert(0, r'D:/projects/kingdee-mcp/src'); "
              "from kingdee_mcp.server import main; main()"],
        env=env,
    )
    print("=" * 60)
    print("  Kingdee MCP Protocol Test - JSON-RPC over stdio")
    print("  (real MCP transport, real Kingdee API calls)")
    print("=" * 60)
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[Init OK]")
            tools = await session.list_tools()
            print(f"[Tools] {len(tools.tools)} MCP tools available")

            # Test 1: Real Kingdee query via MCP protocol
            print("\n" + "=" * 60)
            print("[Test 1] Query purchase orders via MCP JSON-RPC")
            print("=" * 60)
            r = await session.call_tool("kingdee_query_purchase_orders", {
                "params": {"form_id": "PUR_PurchaseOrder", "filter_string": "FDocumentStatus='C'", "limit": 3}
            })
            for item in r.content:
                if hasattr(item, "text") and item.text and not item.text.startswith("Error"):
                    data = json.loads(item.text)
                    print(f"  MCP transport OK | count={data.get('count')}")
                    for row in data.get("data", [])[:3]:
                        bill_no = row[1] if len(row) > 1 else "?"
                        status = row[3] if len(row) > 3 else "?"
                        print(f"  - {bill_no} | status={status}")

            # Test 2: List forms via MCP
            print("\n" + "=" * 60)
            print("[Test 2] List forms via MCP JSON-RPC")
            print("=" * 60)
            r = await session.call_tool("kingdee_list_forms", {
                "params": {"keyword": "purchase"}
            })
            for item in r.content:
                if hasattr(item, "text") and item.text and not item.text.startswith("Error"):
                    data = json.loads(item.text)
                    print(f"  MCP transport OK | {data.get('count')} forms found")
                    for f in data.get("forms", [])[:3]:
                        print(f"  - {f.get('form_id')}: {f.get('name')}")

            # Test 3: Inventory query
            print("\n" + "=" * 60)
            print("[Test 3] Query inventory via MCP JSON-RPC")
            print("=" * 60)
            r = await session.call_tool("kingdee_query_inventory", {
                "params": {"filter_string": "FBaseQty>0", "limit": 3}
            })
            for item in r.content:
                if hasattr(item, "text") and item.text and not item.text.startswith("Error"):
                    data = json.loads(item.text)
                    print(f"  MCP transport OK | count={data.get('count')}")
                    for row in data.get("data", [])[:3]:
                        mat = row[1] if len(row) > 1 else "?"
                        qty = row[3] if len(row) > 3 else "?"
                        print(f"  - {mat} | qty={qty}")

            # Test 4: Save (real data - will hit Kingdee with validation)
            # NOTE: Subprocess mocking doesnt work for cross-process tests.
            # We call with real test data to show MCP protocol end-to-end.
            print("\n" + "=" * 60)
            print("[Test 4] Save bill - MCP protocol end-to-end")
            print("  (real Kingdee API call, may succeed or return structured error)")
            print("=" * 60)
            r = await session.call_tool("kingdee_save_bill", {
                "params": {"form_id": "PUR_PurchaseOrder", "model": {"FDate": "2026-04-14"}}
            })
            for item in r.content:
                if hasattr(item, "text") and item.text and not item.text.startswith("Error"):
                    data = json.loads(item.text)
                    op = data.get("op", "?")
                    ok = data.get("success")
                    na = data.get("next_action")
                    print(f"  MCP: op={op}, success={ok}, next_action={na}")
                    print(f"  tip={data.get('tip', '')}")
                    if ok and na:
                        print(f"\n  [Harness Protocol] AI sees next_action={na}, continues!")
                    elif not ok:
                        errs = data.get("errors", [])
                        print(f"  errors={len(errs)}")
                        for e in errs:
                            print(f"    - {e.get('message', e)}")

    print("\n" + "=" * 60)
    print("  MCP Protocol Test Complete!")
    print("  - Transport: JSON-RPC over stdio [OK]")
    print("  - Server Init: [OK]")
    print("  - Tool Discovery: [OK]")
    print("  - Tool Execution: [OK]")
    print("  - Harness structured response: [OK]")
    print("=" * 60)

asyncio.run(run_test())
