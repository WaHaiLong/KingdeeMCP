# -*- coding: utf-8 -*-
"""Harness Engineering 场景测试"""
import json, asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kingdee_mcp.server import (
    kingdee_list_forms, kingdee_get_fields,
    kingdee_query_purchase_orders, kingdee_query_sale_orders,
    kingdee_query_inventory, kingdee_query_materials,
    kingdee_save_bill, kingdee_push_bill,
    kingdee_query_pending_approvals, kingdee_query_purchase_order_progress,
    kingdee_query_bills,
    QueryInput, FormSearchInput, FieldQueryInput,
    InventoryQueryInput, PurchaseOrderProgressInput,
    WorkflowQueryInput, SaveInput, PushDownInput,
)
from unittest.mock import patch, AsyncMock

async def test():
    # Set env for Kingdee
    os.environ["KINGDEE_SERVER_URL"] = "http://wcl/k3cloud/"
    os.environ["KINGDEE_ACCT_ID"] = "69ae8ed35dab20"
    os.environ["KINGDEE_USERNAME"] = "demo"
    os.environ["KINGDEE_APP_ID"] = "338898_x+bC0diL0pD8x+8EWe3CUayNygSaSDoI"
    os.environ["KINGDEE_APP_SEC"] = "f8b75d4cc5484c98a8803f7b045e06be"
    os.environ["KINGDEE_LCID"] = "2052"

    OK = "[OK]"
    FAIL = "[FAIL]"

    # === 场景1: 发现采购相关表单 ===
    print("\n=== [1] 发现采购相关表单 ===")
    r = await kingdee_list_forms(FormSearchInput(keyword="采购"))
    p = json.loads(r)
    print(f"{OK} 找到 {p['count']} 个表单")
    for f in p['forms'][:5]:
        print(f"   - {f['form_id']}: {f['name']}")

    # === 场景2: 查询本月已审核采购订单 ===
    print("\n=== [2] 查询本月已审核采购订单 ===")
    r = await kingdee_query_purchase_orders(QueryInput(
        form_id='PUR_PurchaseOrder',
        filter_string="FDocumentStatus='C'",
        limit=3
    ))
    p = json.loads(r)
    rows = p.get('data', [])
    print(f"{OK} 返回 {len(rows)} 条记录")
    if rows and isinstance(rows[0], list):
        for row in rows:
            print(f"   - {row}")

    # === 场景3: 执行进度查询 ===
    print("\n=== [3] 采购订单执行进度查询 ===")
    r = await kingdee_query_purchase_order_progress(PurchaseOrderProgressInput(limit=3))
    p = json.loads(r)
    rows = p.get('data', [])
    print(f"{OK} 返回 {len(rows)} 条记录")
    if rows and isinstance(rows[0], list):
        for row in rows[:3]:
            print(f"   - {row}")

    # === 场景4: 即时库存查询 ===
    print("\n=== [4] 即时库存查询 ===")
    r = await kingdee_query_inventory(InventoryQueryInput(filter_string="FBaseQty>0", limit=3))
    p = json.loads(r)
    rows = p.get('data', [])
    print(f"{OK} 返回 {len(rows)} 条库存记录")
    if rows and isinstance(rows[0], list):
        for row in rows:
            print(f"   - {row}")

    # === 场景5: 待审批单据 ===
    print("\n=== [5] 查询待审批单据 ===")
    r = await kingdee_query_pending_approvals(WorkflowQueryInput(status="pending", limit=10))
    p = json.loads(r)
    print(f"{OK} {p['total_forms']} 种单据类型有待审批")
    for form in p.get('results', []):
        if form.get('count', 0) > 0:
            print(f"   - {form['form_name']}: {form['count']} 条")

    # === 场景6: 销售订单查询 ===
    print("\n=== [6] 销售订单查询 ===")
    r = await kingdee_query_sale_orders(QueryInput(
        form_id='SAL_SaleOrder',
        filter_string="FDocumentStatus='C'",
        limit=3
    ))
    p = json.loads(r)
    rows = p.get('data', [])
    print(f"{OK} 返回 {len(rows)} 条销售记录")
    if rows and len(rows) > 0 and isinstance(rows[0], list):
        for row in rows[:3]:
            print(f"   - {row}")
    else:
        print(f"   (无已审核销售订单数据，尝试无过滤查询)")
        r2 = await kingdee_query_sale_orders(QueryInput(form_id='SAL_SaleOrder', limit=5))
        p2 = json.loads(r2)
        rows2 = p2.get('data', [])
        print(f"   无过滤返回 {len(rows2)} 条")
        if rows2 and isinstance(rows2[0], list):
            print(f"   - {rows2[0]}")

    # === 场景7: Save 结构化返回（Harness 约束层核心）===
    print("\n=== [7] Save 结构化返回 - Harness 约束验证 ===")
    api_result = {
        'Result': {
            'ResponseStatus': {'IsSuccess': True, 'Errors': []},
            'Id': 100, 'Number': 'CGDD2026040001'
        }
    }
    with patch('kingdee_mcp.server._post_raw', new_callable=AsyncMock) as mock:
        mock.return_value = api_result
        r = await kingdee_save_bill(SaveInput(
            form_id='PUR_PurchaseOrder',
            model={'FDate': '2026-04-14', 'FSupplierId': {'FNumber': 'S001'}}
        ))
    p = json.loads(r)
    print(f"{OK} op={p['op']}, success={p['success']}")
    print(f"{OK} fid={p.get('fid')}, bill_no={p.get('bill_no')}")
    next_action = p['next_action']
    print(f"{OK} next_action={next_action}")
    if next_action == "submit":
        print(f"{OK} [Harness 生效] Save 后 AI 会看到 next_action=submit，不会误以为操作完成")
    else:
        print(f"{FAIL} next_action 不是 submit，Harness 约束未生效")
    print(f"{OK} tip: {p['tip']}")

    # === 场景8: Push 结构化返回 ===
    print("\n=== [8] Push 结构化返回 - Harness 约束验证 ===")
    api_result = {
        'Result': {
            'ResponseStatus': {'IsSuccess': True, 'Errors': []},
            'Ids': ['300'], 'Numbers': ['CGRKD2026040001']
        }
    }
    with patch('kingdee_mcp.server._post_raw', new_callable=AsyncMock) as mock:
        mock.return_value = api_result
        r = await kingdee_push_bill(PushDownInput(
            form_id='PUR_PurchaseOrder',
            target_form_id='STK_InStock',
            source_bill_nos=['CGDD000025']
        ))
    p = json.loads(r)
    print(f"{OK} op={p['op']}, success={p['success']}")
    print(f"{OK} target_bill_nos={p.get('target_bill_nos')}")
    next_action = p['next_action']
    print(f"{OK} next_action={next_action}")
    if next_action == "submit+audit":
        print(f"{OK} [Harness 生效] Push 后 AI 会看到 next_action=submit+audit，明确知道要继续")
    else:
        print(f"{FAIL} next_action 不是 submit+audit")

    # === 场景9: Save 失败返回（反馈层）===
    print("\n=== [9] Save 失败返回 - Harness 反馈层验证 ===")
    api_result = {
        'Result': {
            'ResponseStatus': {
                'IsSuccess': False,
                'Errors': [{'Message': '物料编码不存在', 'FieldName': 'FMaterialId'}]
            }
        }
    }
    with patch('kingdee_mcp.server._post_raw', new_callable=AsyncMock) as mock:
        mock.return_value = api_result
        r = await kingdee_save_bill(SaveInput(
            form_id='PUR_PurchaseOrder',
            model={'FDate': '2026-04-14', 'FMaterialId': {'FNumber': 'MAT999'}}
        ))
    p = json.loads(r)
    print(f"{OK} success={p['success']} (应为 False)")
    print(f"{OK} errors={len(p.get('errors', []))} 条")
    for e in p.get('errors', []):
        print(f"   - [{e.get('type', '?')}] {e.get('message', '?')}")
    if p.get('errors') and len(p['errors']) > 0:
        first_err = p['errors'][0]
        if first_err.get('matched'):
            m = first_err['matched']
            print(f"{OK} [Harness 反馈层] matched reason: {m.get('reason')}")
            print(f"{OK} [Harness 反馈层] matched suggestion: {m.get('suggestion')}")
        else:
            print(f"{OK} [Harness 反馈层] error message: {first_err.get('message')}")
    print(f"{OK} tip: {p.get('tip', '')}")

    print("\n" + "=" * 60)
    print("全部场景测试完成")
    print("=" * 60)

asyncio.run(test())