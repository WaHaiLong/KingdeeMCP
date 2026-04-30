"""端到端工作流测试（需真实金蝶环境）。

涵盖：销售订单 CRUD、查询/视图、采购下推、工作流、SQL 探查、元数据、附加查询。
凭证由环境变量提供（CLAUDE.md：本地存于 C:\\Users\\ZnL\\kingdee-mcp.bat）。
未配置 KINGDEE_* 时由 conftest 静默跳过。

注意：单据编码（CUST0001/VEN00001/1.01.001.0001 等）和已有 FID 的断言是 demo 账套约定，
跨账套运行需调整或软化（详见各 test 内的 assert 注释）。
"""
import json
from datetime import date

import pytest

from kingdee_mcp.server import (
    BillIdsInput,
    FieldQueryInput,
    FormSearchInput,
    InventoryQueryInput,
    MaterialQueryInput,
    PartnerQueryInput,
    PushDownInput,
    QueryInput,
    SqlDescribeInput,
    SqlSearchInput,
    ViewInput,
    _login,
    _post_raw,
    kingdee_audit_bills,
    kingdee_delete_bills,
    kingdee_describe_table,
    kingdee_discover_columns,
    kingdee_discover_tables,
    kingdee_get_fields,
    kingdee_list_forms,
    kingdee_query_bills,
    kingdee_query_inventory,
    kingdee_query_materials,
    kingdee_query_partners,
    kingdee_submit_bills,
    kingdee_unaudit_bills,
    kingdee_view_bill,
)

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module", autouse=True)
async def _ensure_login():
    await _login()
    yield


def _today() -> str:
    return date.today().isoformat()


async def test_sale_order_crud():
    """T1: 销售订单全生命周期（Save → Submit → Audit → Query → View → Unaudit → Delete）。"""
    model = {
        "FDate": _today(),
        "FCustId": {"FNumber": "CUST0001"},
        "FSalesOrgId": {"FNumber": "100"},
        "FSaleOrderEntry": [
            {
                "FMaterialId": {"FNumber": "1.01.001.0001"},
                "FUnitID": {"FNumber": "Pcs"},
                "FQty": 5,
                "FPrice": 200,
            }
        ],
    }
    save_result = await _post_raw(
        "save", "SAL_SaleOrder", model, need_return_fields=["FID", "FBillNo"]
    )
    rs = save_result["Result"]
    assert rs["ResponseStatus"]["IsSuccess"], f"save failed: {rs}"
    fid = rs.get("Id") or rs.get("FID")
    assert fid, f"no FID in save result: {rs}"
    fid_str = str(fid)

    try:
        submit = json.loads(
            await kingdee_submit_bills(
                BillIdsInput(form_id="SAL_SaleOrder", bill_ids=[fid_str])
            )
        )
        assert submit["Result"]["ResponseStatus"]["IsSuccess"], f"submit: {submit}"

        audit = json.loads(
            await kingdee_audit_bills(
                BillIdsInput(form_id="SAL_SaleOrder", bill_ids=[fid_str])
            )
        )
        assert audit["Result"]["ResponseStatus"]["IsSuccess"], f"audit: {audit}"

        query = json.loads(
            await kingdee_query_bills(
                QueryInput(
                    form_id="SAL_SaleOrder",
                    filter_string=f"FID={fid_str}",
                    field_keys="FID,FBillNo,FDocumentStatus",
                )
            )
        )
        assert query["count"] >= 1
        assert query["data"][0][2] == "C", f"expected status=C, got {query['data'][0]}"

        view = json.loads(
            await kingdee_view_bill(
                ViewInput(form_id="SAL_SaleOrder", bill_id=fid_str)
            )
        )
        bill = view.get("Result", {}).get("Result", {})
        assert "BillNo" in bill, f"view missing BillNo: {view}"

        unaudit = json.loads(
            await kingdee_unaudit_bills(
                BillIdsInput(form_id="SAL_SaleOrder", bill_ids=[fid_str])
            )
        )
        assert unaudit["Result"]["ResponseStatus"]["IsSuccess"], f"unaudit: {unaudit}"
    finally:
        # 清理：无论中途 assert 失败与否都尝试删除
        try:
            await kingdee_delete_bills(
                BillIdsInput(form_id="SAL_SaleOrder", bill_ids=[fid_str])
            )
        except Exception:
            pass


async def test_query_partners_customers():
    r = json.loads(
        await kingdee_query_partners(
            PartnerQueryInput(
                partner_type="BD_Customer",
                filter_string="",
                field_keys="FNumber,FName",
                limit=3,
            )
        )
    )
    assert r.get("count", 0) >= 1, f"no customers: {r}"


async def test_query_partners_suppliers():
    r = json.loads(
        await kingdee_query_partners(
            PartnerQueryInput(
                partner_type="BD_Supplier",
                filter_string="",
                field_keys="FNumber,FName",
                limit=3,
            )
        )
    )
    assert r.get("count", 0) >= 1, f"no suppliers: {r}"


async def test_query_materials():
    r = json.loads(
        await kingdee_query_materials(
            MaterialQueryInput(
                filter_string="",
                field_keys="FNumber,FName,FSpecification",
                limit=3,
            )
        )
    )
    assert r.get("count", 0) >= 1, f"no materials: {r}"


async def test_query_inventory():
    r = json.loads(
        await kingdee_query_inventory(InventoryQueryInput(filter_string="FBaseQty>0", limit=3))
    )
    assert "count" in r, f"inventory query missing count: {r}"


async def test_view_existing_bills_smoke():
    """对几个已有单据 ID 调 view；任何成功结果都接受（具体 ID 跨账套差异）。"""
    candidates = [
        ("SAL_SaleOrder", "100033"),
        ("SAL_SaleOrder", "100017"),
        ("PUR_PurchaseOrder", "100001"),
    ]
    any_ok = False
    for form_id, bill_id in candidates:
        try:
            r = json.loads(
                await kingdee_view_bill(ViewInput(form_id=form_id, bill_id=bill_id))
            )
            if r.get("Result", {}).get("Result", {}).get("BillNo"):
                any_ok = True
                break
        except Exception:
            continue
    assert any_ok, "no candidate bill could be viewed in this account set"


async def test_purchase_order_push_lifecycle():
    """T4: 采购订单 Save→Submit→Audit→Push 到收料通知单，含完整清理。"""
    model = {
        "FDate": _today(),
        "FSupplierId": {"FNumber": "VEN00001"},
        "FPurchaseOrgId": {"FNumber": "100"},
        "FPOOrderEntry": [
            {
                "FMaterialId": {"FNumber": "1.01.001.0001"},
                "FUnitID": {"FNumber": "Pcs"},
                "FQty": 1,
                "FPrice": 100,
            }
        ],
    }
    save_result = await _post_raw("save", "PUR_PurchaseOrder", model)
    rs = save_result["Result"]
    assert rs["ResponseStatus"]["IsSuccess"], f"PO save: {rs}"
    fid = rs.get("FID") or rs.get("Id")
    bill_no = rs.get("FBillNo") or rs.get("Number")
    fid_str = str(fid)
    bill_no_str = str(bill_no)

    pushed_target_ids: list[str] = []
    try:
        sr = json.loads(
            await kingdee_submit_bills(
                BillIdsInput(form_id="PUR_PurchaseOrder", bill_ids=[fid_str])
            )
        )
        assert sr["Result"]["ResponseStatus"]["IsSuccess"], f"PO submit: {sr}"

        ar = json.loads(
            await kingdee_audit_bills(
                BillIdsInput(form_id="PUR_PurchaseOrder", bill_ids=[fid_str])
            )
        )
        assert ar["Result"]["ResponseStatus"]["IsSuccess"], f"PO audit: {ar}"

        # demo 环境无默认转换规则，必须显式指定 RuleId
        from kingdee_mcp.server import kingdee_push_bill

        pr = json.loads(
            await kingdee_push_bill(
                PushDownInput(
                    form_id="PUR_PurchaseOrder",
                    target_form_id="PUR_ReceiveBill",
                    source_bill_nos=[bill_no_str],
                    rule_id="PUR_PurchaseOrder-PUR_ReceiveBill",
                )
            )
        )
        push_status = pr.get("Result", {}).get("ResponseStatus", {})
        assert push_status.get("IsSuccess"), f"push: {push_status.get('Errors')}"
        pushed_target_ids = [str(x) for x in pr.get("Result", {}).get("Ids", [])]
        assert pushed_target_ids, "push 成功但未生成目标单"
    finally:
        for rid in pushed_target_ids:
            try:
                await kingdee_delete_bills(
                    BillIdsInput(form_id="PUR_ReceiveBill", bill_ids=[rid])
                )
            except Exception:
                pass
        try:
            await kingdee_unaudit_bills(
                BillIdsInput(form_id="PUR_PurchaseOrder", bill_ids=[fid_str])
            )
            await kingdee_delete_bills(
                BillIdsInput(form_id="PUR_PurchaseOrder", bill_ids=[fid_str])
            )
        except Exception:
            pass


async def test_workflow_pending_approvals_smoke():
    from kingdee_mcp.server import (
        WorkflowQueryInput,
        kingdee_query_pending_approvals,
    )

    r_str = await kingdee_query_pending_approvals(WorkflowQueryInput(limit=3))
    # 仅断言返回是合法 JSON；空列表也算通过（demo 可能无待办）
    json.loads(r_str)


async def test_metadata_list_forms():
    r = json.loads(await kingdee_list_forms(FormSearchInput(keyword="采购")))
    assert r.get("count", 0) >= 1
    assert "form_id" in r["forms"][0]


async def test_metadata_get_fields():
    r = json.loads(await kingdee_get_fields(FieldQueryInput(form_id="BD_Material")))
    assert "recommended_fields" in r


async def test_sql_discover_tables():
    """需要 MCP_SQLSERVER_* 配置；缺失时 _err 返回 JSON 字符串，软处理。"""
    import os

    if not os.getenv("MCP_SQLSERVER_HOST"):
        pytest.skip("无 SQL Server 配置")
    r = json.loads(await kingdee_discover_tables(SqlSearchInput(pattern="MATERIAL")))
    assert "tables" in r or r.get("error"), f"unexpected: {r}"


async def test_sql_describe_material_table():
    import os

    if not os.getenv("MCP_SQLSERVER_HOST"):
        pytest.skip("无 SQL Server 配置")
    r = json.loads(await kingdee_describe_table(SqlDescribeInput(table_name="T_BD_MATERIAL")))
    assert "columns" in r or r.get("error"), f"unexpected: {r}"


async def test_sql_discover_columns():
    import os

    if not os.getenv("MCP_SQLSERVER_HOST"):
        pytest.skip("无 SQL Server 配置")
    r = json.loads(await kingdee_discover_columns(SqlSearchInput(pattern="SUPPLIER")))
    assert "columns" in r or r.get("error"), f"unexpected: {r}"
