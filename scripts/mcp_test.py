# -*- coding: utf-8 -*-
"""
MCP 场景测试 - 我来扮演 AI 用户，测试 kingdee-mcp 的各个场景
"""
import json, asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# 设置环境变量
os.environ["KINGDEE_SERVER_URL"] = "http://wcl/k3cloud/"
os.environ["KINGDEE_ACCT_ID"] = "69ae8ed35dab20"
os.environ["KINGDEE_USERNAME"] = "demo"
os.environ["KINGDEE_APP_ID"] = "338898_x+bC0diL0pD8x+8EWe3CUayNygSaSDoI"
os.environ["KINGDEE_APP_SEC"] = "f8b75d4cc5484c98a8803f7b045e06be"
os.environ["KINGDEE_LCID"] = "2052"

from kingdee_mcp.server import (
    kingdee_list_forms, kingdee_get_fields,
    kingdee_query_purchase_orders, kingdee_query_sale_orders,
    kingdee_query_bills, kingdee_query_inventory,
    kingdee_save_bill, kingdee_submit_bills, kingdee_audit_bills,
    kingdee_push_bill, kingdee_unaudit_bills,
    kingdee_query_pending_approvals, kingdee_query_purchase_order_progress,
    kingdee_view_bill,
    QueryInput, FormSearchInput, FieldQueryInput,
    InventoryQueryInput, PurchaseOrderProgressInput,
    WorkflowQueryInput, ViewInput, SaveInput,
    PushDownInput, BillIdsInput,
)
from unittest.mock import patch, AsyncMock


async def user_says(message: str):
    """模拟用户说了一句话"""
    print(f"\n{'='*60}")
    print(f"[用户] {message}")
    print(f"{'='*60}")


async def ai_action(name: str, func, *args, **kwargs):
    """模拟 AI 执行了一个动作"""
    print(f"\n[AI 动作] {name}")
    result = await func(*args, **kwargs)
    parsed = json.loads(result)
    return parsed


async def main():
    print("\n" + "="*60)
    print("  Kingdee MCP 场景测试 - 我是 AI，我来操作金蝶系统")
    print("="*60)

    # ══════════════════════════════════════════════════════
    # 场景1：用户发现表单
    # ══════════════════════════════════════════════════════
    await user_says("查询有哪些采购相关的表单")

    r = await ai_action("调用 kingdee_list_forms", kingdee_list_forms,
                         FormSearchInput(keyword="采购"))
    print(f"  找到 {r['count']} 个表单:")
    for f in r['forms'][:5]:
        print(f"    - {f['form_id']}: {f['name']}")

    # ══════════════════════════════════════════════════════
    # 场景2：用户查询数据
    # ══════════════════════════════════════════════════════
    await user_says("查一下本月所有已审核的采购订单，按日期倒序排列")

    r = await ai_action("调用 kingdee_query_purchase_orders", kingdee_query_purchase_orders,
                         QueryInput(form_id="PUR_PurchaseOrder",
                                   filter_string="FDocumentStatus='C'",
                                   order_string="FDate DESC",
                                   limit=10))
    print(f"  返回 {r['count']} 条记录:")
    if r['data'] and len(r['data']) > 0:
        if isinstance(r['data'][0], list):
            # 列表格式: [FID, FBillNo, FDate, FDocumentStatus, FSupplierId.FName, ...]
            print(f"  {'单据号':<20} {'日期':<12} {'状态':<6} {'供应商'}")
            print(f"  {'-'*60}")
            for row in r['data'][:5]:
                bill_no = row[1] if len(row) > 1 else "?"
                date = row[2] if len(row) > 2 else "?"
                status = row[3] if len(row) > 3 else "?"
                supplier = row[4] if len(row) > 4 else "?"
                status_map = {"A": "创建", "B": "审核中", "C": "已审核", "D": "重新审核", "Z": "暂存"}
                status_name = status_map.get(status, status)
                print(f"  {bill_no:<20} {str(date):<12} {status_name:<6} {supplier}")
    else:
        print(f"  (无数据)")

    # ══════════════════════════════════════════════════════
    # 场景3：用户查询执行进度
    # ══════════════════════════════════════════════════════
    await user_says("查询采购订单 CGDD000025 的执行进度")

    r = await ai_action("调用 kingdee_query_purchase_order_progress",
                         kingdee_query_purchase_order_progress,
                         PurchaseOrderProgressInput(limit=5))

    # 先找到 CGDD000025
    target_rows = [row for row in r.get('data', []) if len(row) > 1 and row[1] == "CGDD000025"]
    if target_rows:
        row = target_rows[0]
        # 字段: FID, FBillNo, FDate, FDocumentStatus, FSupplierId.FName,
        #       FMaterialId.FNumber, FMaterialId.FName, FQty, FReceiveQty, FStockInQty,
        #       FPrice, FTaxPrice, FAllAmount
        mat = row[6] if len(row) > 6 else "?"
        qty = row[7] if len(row) > 7 else "?"
        recv = row[8] if len(row) > 8 else "?"
        stock = row[9] if len(row) > 9 else "?"
        print(f"  单据: CGDD000025")
        print(f"  物料: {mat}")
        print(f"  订单数量: {qty}")
        print(f"  累计收料: {recv}")
        print(f"  累计入库: {stock}")
        link_qty = (float(recv or 0) + float(stock or 0)) if recv and stock else 0
        print(f"  关联数量: {link_qty} (={recv}+{stock})")
        if float(qty or 0) > 0:
            pct = link_qty / float(qty) * 100
            print(f"  执行进度: {pct:.1f}%")
    else:
        print(f"  未找到 CGDD000025，返回了 {r['count']} 条记录")
        for row in r.get('data', [])[:3]:
            print(f"    {row}")

    # ══════════════════════════════════════════════════════
    # 场景4：用户查询库存
    # ══════════════════════════════════════════════════════
    await user_says("查一下当前有哪些物料有库存")

    r = await ai_action("调用 kingdee_query_inventory", kingdee_query_inventory,
                         InventoryQueryInput(filter_string="FBaseQty>0", limit=10))
    print(f"  返回 {r['count']} 条库存记录:")
    if r['data'] and len(r['data']) > 0:
        # STK_Inventory 字段: FMaterialId.FNumber, FMaterialId.FName, FStockId.FName, FBaseQty, FBaseUnitId.FName
        if isinstance(r['data'][0], list):
            print(f"  {'物料编码':<12} {'物料名称':<20} {'仓库':<12} {'数量':<8} {'单位'}")
            print(f"  {'-'*60}")
            for row in r['data'][:5]:
                mat_num = row[0] if len(row) > 0 else "?"
                mat_name = row[1] if len(row) > 1 else "?"
                stock = row[2] if len(row) > 2 else "?"
                qty = row[3] if len(row) > 3 else "?"
                unit = row[4] if len(row) > 4 else "?"
                print(f"  {mat_num:<12} {mat_name:<20} {stock:<12} {qty:<8} {unit}")

    # ══════════════════════════════════════════════════════
    # 场景5：用户查询待审批
    # ══════════════════════════════════════════════════════
    await user_says("查一下有哪些待审批的单据")

    r = await ai_action("调用 kingdee_query_pending_approvals", kingdee_query_pending_approvals,
                         WorkflowQueryInput(status="pending", limit=10))
    print(f"  共 {r['total_forms']} 种单据类型有待审批:")
    pending_total = 0
    for form in r.get('results', []):
        if form.get('count', 0) > 0:
            print(f"    - {form['form_name']}: {form['count']} 条")
            pending_total += form['count']
    if pending_total == 0:
        print(f"    (暂无待审批单据)")

    # ══════════════════════════════════════════════════════
    # 场景6：用户新建采购订单（核心 Harness 场景！）
    # ══════════════════════════════════════════════════════
    await user_says("帮我新建一张采购订单，供应商是S001，物料MAT001，数量100，单价50")

    # 模拟 Kingdee API 返回（保存成功）
    api_result = {
        'Result': {
            'ResponseStatus': {'IsSuccess': True, 'Errors': []},
            'Id': 100120, 'Number': 'CGDD2026040001'
        }
    }
    with patch('kingdee_mcp.server._post_raw', new_callable=AsyncMock) as mock:
        mock.return_value = api_result
        r = await ai_action("调用 kingdee_save_bill", kingdee_save_bill,
                             SaveInput(
                                 form_id="PUR_PurchaseOrder",
                                 model={
                                     "FDate": "2026-04-14",
                                     "FSupplierId": {"FNumber": "S001"},
                                     "FPOOrderEntry": [
                                         {
                                             "FMaterialId": {"FNumber": "MAT001"},
                                             "FQty": 100,
                                             "FPrice": 50,
                                             "FTaxRate": 13,
                                             "FUnitID": {"FNumber": "PCS"}
                                         }
                                     ]
                                 }
                             ))

    print(f"\n  【Harness 约束层生效！】")
    print(f"  op: {r['op']}")
    print(f"  success: {r['success']}")
    print(f"  fid: {r.get('fid')}")
    print(f"  bill_no: {r.get('bill_no')}")
    print(f"  next_action: {r['next_action']}")
    print(f"  next_action_desc: {r.get('next_action_desc', '')}")
    print(f"  tip: {r.get('tip', '')}")

    if r['next_action'] == 'submit':
        print(f"\n  [AI 判断] next_action=submit，说明单据还在草稿状态，")
        print(f"           需要继续调用 kingdee_submit_bills 提交单据")
        print(f"           而不能认为'操作已完成'")
        print(f"           这就是 Harness Engineering 防止目标漂移的核心机制！")

        # AI 自动继续：提交
        await user_says("继续提交这张单据")
        api_result2 = {
            'Result': {
                'ResponseStatus': {'IsSuccess': True, 'Errors': []},
                'Ids': ['100120']
            }
        }
        with patch('kingdee_mcp.server._post_raw', new_callable=AsyncMock) as mock:
            mock.return_value = api_result2
            r2 = await ai_action("调用 kingdee_submit_bills", kingdee_submit_bills,
                                  BillIdsInput(form_id="PUR_PurchaseOrder", bill_ids=["100120"]))
        print(f"\n  【提交结果】")
        print(f"  op: {r2['op']}")
        print(f"  success: {r2['success']}")
        print(f"  next_action: {r2['next_action']}")
        print(f"  tip: {r2.get('tip', '')}")

        if r2['next_action'] == 'audit':
            print(f"\n  [AI 判断] next_action=audit，")
            print(f"           需要继续调用 kingdee_audit_bills 审核单据")

            # AI 自动继续：审核
            await user_says("继续审核这张单据")
            api_result3 = {
                'Result': {
                    'ResponseStatus': {'IsSuccess': True, 'Errors': []},
                    'Ids': ['100120']
                }
            }
            with patch('kingdee_mcp.server._post_raw', new_callable=AsyncMock) as mock:
                mock.return_value = api_result3
                r3 = await ai_action("调用 kingdee_audit_bills", kingdee_audit_bills,
                                      BillIdsInput(form_id="PUR_PurchaseOrder", bill_ids=["100120"]))
            print(f"\n  【审核结果】")
            print(f"  op: {r3['op']}")
            print(f"  success: {r3['success']}")
            print(f"  next_action: {r3['next_action']}")
            print(f"  tip: {r3.get('tip', '')}")

            if r3['next_action'] is None:
                print(f"\n  【完成！】next_action=null，单据生命周期结束，流程完成！")

    # ══════════════════════════════════════════════════════
    # 场景7：用户下推操作（另一个核心 Harness 场景！）
    # ══════════════════════════════════════════════════════
    await user_says("把这张采购订单 CGDD000025 下推生成采购入库单")

    api_result = {
        'Result': {
            'ResponseStatus': {'IsSuccess': True, 'Errors': []},
            'Ids': ['300001'], 'Numbers': ['CGRKD2026040001']
        }
    }
    with patch('kingdee_mcp.server._post_raw', new_callable=AsyncMock) as mock:
        mock.return_value = api_result
        r = await ai_action("调用 kingdee_push_bill", kingdee_push_bill,
                             PushDownInput(
                                 form_id="PUR_PurchaseOrder",
                                 target_form_id="STK_InStock",
                                 source_bill_nos=["CGDD000025"]
                             ))

    print(f"\n  【Harness 约束层生效！】")
    print(f"  op: {r['op']}")
    print(f"  success: {r['success']}")
    print(f"  source_bill_nos: {r.get('source_bill_nos')}")
    print(f"  target_form_id: {r.get('target_form_id')}")
    print(f"  target_bill_nos: {r.get('target_bill_nos')}")
    print(f"  target_fids: {r.get('target_fids')}")
    print(f"  next_action: {r['next_action']}")
    print(f"  tip: {r.get('tip', '')}")

    if r['next_action'] == 'submit+audit':
        print(f"\n  [AI 判断] next_action=submit+audit，")
        print(f"           必须继续提交 + 审核，不能在下推后就停止！")
        print(f"           这是防止'过早宣布胜利'的关键机制")

    # ══════════════════════════════════════════════════════
    # 场景8：错误处理（反馈层验证）
    # ══════════════════════════════════════════════════════
    await user_says("尝试用不存在的物料编码新建订单")

    api_result = {
        'Result': {
            'ResponseStatus': {
                'IsSuccess': False,
                'Errors': [{
                    'Message': '物料编码不存在',
                    'FieldName': 'FMaterialId',
                    'Dsc': 'FMaterialId.L: invalid value'
                }]
            }
        }
    }
    with patch('kingdee_mcp.server._post_raw', new_callable=AsyncMock) as mock:
        mock.return_value = api_result
        r = await ai_action("调用 kingdee_save_bill（会失败）", kingdee_save_bill,
                             SaveInput(
                                 form_id="PUR_PurchaseOrder",
                                 model={
                                     "FDate": "2026-04-14",
                                     "FSupplierId": {"FNumber": "S001"},
                                     "FMaterialId": {"FNumber": "MAT999_NOT_EXIST"}
                                 }
                             ))

    print(f"\n  【Harness 反馈层生效！】")
    print(f"  success: {r['success']} (应为 False)")
    print(f"  errors: {len(r.get('errors', []))} 条")
    for e in r.get('errors', []):
        print(f"    - [{e.get('type', '?')}] {e.get('message', '?')}")
        if e.get('matched'):
            print(f"      reason: {e['matched'].get('reason', '')}")
            print(f"      suggestion: {e['matched'].get('suggestion', '')}")
    print(f"  tip: {r.get('tip', '')}")

    print(f"\n  [AI 判断] 错误有 reason 和 suggestion，")
    print(f"           AI 可以据此修正，而不是盲目重试")

    print("\n" + "="*60)
    print("  所有场景测试完成！")
    print("="*60)
    print("""
  总结：Harness Engineering 防止目标漂移的三层机制：

  1. 约束层 (DOC_LIFECYCLE)
     - 操作返回 next_action，引导下一步
     - AI 不会在 Save/Push 后误以为完成

  2. 反馈层 (KNOWN_ERROR_PATTERNS)
     - 错误返回 reason + suggestion
     - AI 知道为什么会错、怎么修正

  3. 上下文层 (workflow-hints.md)
     - 按需检索，不是静态入口
     - 操作完成后有验证步骤
""")


asyncio.run(main())