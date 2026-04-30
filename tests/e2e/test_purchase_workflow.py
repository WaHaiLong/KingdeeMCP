"""复合工作流 E2E：覆盖最易翻车的 push 路径。

流程：
1. kingdee_create_and_audit 创建并审核采购订单
2. kingdee_push_and_audit 下推 + 审核生成收料通知单
3. assert 目标单 FDocumentStatus == "C"（已审核）

凭证由环境变量提供，无 KINGDEE_* 时由 conftest 自动 skip。
"""
import json
from datetime import date

import pytest

from kingdee_mcp.server import (
    BillIdsInput,
    CreateAndAuditInput,
    PushAndAuditInput,
    QueryInput,
    _login,
    kingdee_create_and_audit,
    kingdee_delete_bills,
    kingdee_push_and_audit,
    kingdee_query_bills,
    kingdee_unaudit_bills,
)

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module", autouse=True)
async def _ensure_login():
    await _login()
    yield


def _today() -> str:
    return date.today().isoformat()


async def test_create_and_push_purchase_order_full_lifecycle():
    """复合工具一站式：PO 创建+审核 → 下推+审核收料通知单 → 验状态 → 清理。"""
    po_model = {
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

    create_resp = json.loads(
        await kingdee_create_and_audit(
            CreateAndAuditInput(form_id="PUR_PurchaseOrder", model=po_model)
        )
    )
    assert create_resp["success"], (
        f"create_and_audit failed at {create_resp.get('halted_at')}: "
        f"errors={create_resp.get('errors')} hint={create_resp.get('recovery_hint')}"
    )
    assert create_resp["halted_at"] is None
    assert create_resp["next_action"] is None, "复合工具完成后 next_action 应为 null"
    # 三步都应记录
    step_ops = [s["op"] for s in create_resp["steps"]]
    assert step_ops == ["save", "submit", "audit"], f"unexpected steps: {step_ops}"

    po_fid = str(create_resp["fid"])
    po_bill_no = str(create_resp["bill_no"])

    pushed_target_fids: list[str] = []
    try:
        push_resp = json.loads(
            await kingdee_push_and_audit(
                PushAndAuditInput(
                    form_id="PUR_PurchaseOrder",
                    target_form_id="PUR_ReceiveBill",
                    source_bill_nos=[po_bill_no],
                    rule_id="PUR_PurchaseOrder-PUR_ReceiveBill",
                )
            )
        )
        assert push_resp["success"], (
            f"push_and_audit failed at {push_resp.get('halted_at')}: "
            f"errors={push_resp.get('errors')} hint={push_resp.get('recovery_hint')}"
        )
        assert push_resp["halted_at"] is None
        push_step_ops = [s["op"] for s in push_resp["steps"]]
        assert push_step_ops == ["push", "submit", "audit"], (
            f"unexpected push steps: {push_step_ops}"
        )

        pushed_target_fids = [str(x) for x in push_resp.get("target_fids", [])]
        assert pushed_target_fids, "push 成功但未返回 target_fids"

        # 验目标单已审核 (FDocumentStatus = 'C')
        target_fid = pushed_target_fids[0]
        query = json.loads(
            await kingdee_query_bills(
                QueryInput(
                    form_id="PUR_ReceiveBill",
                    filter_string=f"FID={target_fid}",
                    field_keys="FID,FBillNo,FDocumentStatus",
                )
            )
        )
        assert query["count"] >= 1, f"目标单 FID={target_fid} 查不到: {query}"
        assert query["data"][0][2] == "C", (
            f"目标单未达已审核状态，实际={query['data'][0][2]}: {query['data'][0]}"
        )
    finally:
        # 清理：先反审核+删目标单，再反审核+删源单
        for rid in pushed_target_fids:
            try:
                await kingdee_unaudit_bills(
                    BillIdsInput(form_id="PUR_ReceiveBill", bill_ids=[rid])
                )
            except Exception:
                pass
            try:
                await kingdee_delete_bills(
                    BillIdsInput(form_id="PUR_ReceiveBill", bill_ids=[rid])
                )
            except Exception:
                pass
        try:
            await kingdee_unaudit_bills(
                BillIdsInput(form_id="PUR_PurchaseOrder", bill_ids=[po_fid])
            )
        except Exception:
            pass
        try:
            await kingdee_delete_bills(
                BillIdsInput(form_id="PUR_PurchaseOrder", bill_ids=[po_fid])
            )
        except Exception:
            pass
