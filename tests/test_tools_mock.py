"""
Kingdee MCP Server 工具测试（mock 模式）
测试各工具在模拟 API 响应下的行为
"""

import json
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kingdee_mcp.server import (
    kingdee_query_purchase_orders, kingdee_query_sale_orders,
    kingdee_query_bills, kingdee_view_bill,
    kingdee_save_bill, kingdee_audit_bills, kingdee_submit_bills,
    kingdee_unaudit_bills, kingdee_delete_bills, kingdee_push_bill,
    kingdee_create_and_audit, kingdee_push_and_audit,
    QueryInput, ViewInput, SaveInput, BillIdsInput, PushDownInput,
    CreateAndAuditInput, PushAndAuditInput,
)


# ─── Mock HTTP 响应工厂 ─────────────────────────────────

def mock_kingdee_response(result_data: dict):
    """返回一个模拟的金蝶 API 响应"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = result_data
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def mock_httpx_async_client(response_data: dict):
    """返回一个模拟的 AsyncClient，能拦截 post 调用"""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=mock_kingdee_response(response_data))
    return client


# ─── kingdee_query_purchase_orders ──────────────────────

class TestQueryPurchaseOrders:
    @pytest.mark.asyncio
    async def test_returns_formatted_json(self):
        api_result = {
            "Result": [
                {"FID": "1", "FBillNo": "PO001", "FSupplierId.FName": "华强"},
                {"FID": "2", "FBillNo": "PO002", "FSupplierId.FName": "天河"},
            ]
        }
        with patch("kingdee_mcp.server._post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_query_purchase_orders(
                QueryInput(form_id="PUR_PurchaseOrder")
            )
        parsed = json.loads(result)
        assert parsed["count"] == 2
        assert parsed["data"][0]["FBillNo"] == "PO001"

    @pytest.mark.asyncio
    async def test_has_more_when_limit_reached(self):
        api_result = {"Result": [{"FID": str(i)} for i in range(20)]}
        with patch("kingdee_mcp.server._post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_query_purchase_orders(
                QueryInput(form_id="PUR_PurchaseOrder", limit=20)
            )
        parsed = json.loads(result)
        assert parsed["has_more"] is True

    @pytest.mark.asyncio
    async def test_no_more_when_under_limit(self):
        api_result = {"Result": [{"FID": str(i)} for i in range(5)]}
        with patch("kingdee_mcp.server._post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_query_purchase_orders(
                QueryInput(form_id="PUR_PurchaseOrder", limit=20)
            )
        parsed = json.loads(result)
        assert parsed["has_more"] is False


# ─── kingdee_query_sale_orders ──────────────────────────

class TestQuerySaleOrders:
    @pytest.mark.asyncio
    async def test_returns_customer_name(self):
        api_result = {
            "Result": [
                {"FID": "1", "FBillNo": "SO001", "FCustId.FName": "上海客户"},
            ]
        }
        with patch("kingdee_mcp.server._post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_query_sale_orders(
                QueryInput(form_id="SAL_SaleOrder")
            )
        parsed = json.loads(result)
        assert parsed["data"][0]["FCustId.FName"] == "上海客户"


# ─── kingdee_query_bills ───────────────────────────────

class TestQueryBills:
    @pytest.mark.asyncio
    async def test_generic_query_with_custom_fields(self):
        api_result = {"Result": [{"FID": "1", "FBillNo": "B001"}]}
        with patch("kingdee_mcp.server._post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_query_bills(
                QueryInput(
                    form_id="PUR_PurchaseOrder",
                    field_keys="FID,FBillNo,FDate",
                    filter_string="FDocumentStatus='C'",
                )
            )
        parsed = json.loads(result)
        assert parsed["count"] == 1
        assert parsed["form_id"] == "PUR_PurchaseOrder"

    @pytest.mark.asyncio
    async def test_api_error_returns_err_string(self):
        with patch("kingdee_mcp.server._post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("连接失败")
            result = await kingdee_query_bills(
                QueryInput(form_id="PUR_PurchaseOrder")
            )
        # 新的错误格式是 {"error": true, "errors": [...]}，不是 "错误：..."
        assert '"error": true' in result
        assert '"errors"' in result


# ─── kingdee_view_bill ─────────────────────────────────

class TestViewBill:
    @pytest.mark.asyncio
    async def test_returns_full_bill_details(self):
        # Kingdee View API (raw JSON): {"Result": {"ResponseStatus": {...}, "Result": {...bill...}}}
        api_result = {
            "Result": {
                "ResponseStatus": {"IsSuccess": True, "Errors": []},
                "Result": {
                    "Id": "1",
                    "FBillNo": "PO001",
                    "FDate": "2026-03-01",
                    "SupplierId": {"Number": "VEN001"},
                },
            }
        }
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_view_bill(
                ViewInput(form_id="PUR_PurchaseOrder", bill_id="1")
            )
        parsed = json.loads(result)
        assert parsed["Result"]["Result"]["FBillNo"] == "PO001"


# ─── kingdee_save_bill ─────────────────────────────────

class TestSaveBill:
    @pytest.mark.asyncio
    async def test_create_returns_fid_and_billno(self):
        # Kingdee Save API (raw JSON) 返回 {"Result": {"ResponseStatus": {...}, "Id": ..., "Number": ...}}
        api_result = {
            "Result": {
                "ResponseStatus": {"IsSuccess": True, "Errors": []},
                "Id": 100,
                "Number": "CGDD2026030001",
            }
        }
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_save_bill(
                SaveInput(
                    form_id="PUR_PurchaseOrder",
                    model={"FDate": "2026-03-01", "FSupplierId": {"FNumber": "S001"}},
                )
            )
        parsed = json.loads(result)
        assert parsed["op"] == "save"
        assert parsed["success"] is True
        assert parsed["fid"] == 100
        assert parsed["bill_no"] == "CGDD2026030001"
        assert parsed["next_action"] == "submit"

    @pytest.mark.asyncio
    async def test_save_failure_returns_errors(self):
        api_result = {
            "Result": {
                "ResponseStatus": {
                    "IsSuccess": False,
                    "Errors": [{"FieldName": "FMaterialId", "Message": "物料编码不存在"}],
                }
            }
        }
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_save_bill(
                SaveInput(
                    form_id="PUR_PurchaseOrder",
                    model={"FDate": "2026-03-01"},
                )
            )
        parsed = json.loads(result)
        assert parsed["success"] is False
        assert len(parsed["errors"]) == 1


# ─── kingdee_audit_bills ────────────────────────────────

class TestAuditBills:
    @pytest.mark.asyncio
    async def test_audit_returns_success(self):
        api_result = {
            "Result": {
                "ResponseStatus": {"IsSuccess": True, "Errors": []},
                "Ids": ["1", "2"],
            }
        }
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_audit_bills(
                BillIdsInput(form_id="PUR_PurchaseOrder", bill_ids=["1", "2"])
            )
        parsed = json.loads(result)
        assert parsed["op"] == "audit"
        assert parsed["success"] is True
        assert parsed["bill_ids"] == ["1", "2"]
        assert parsed["next_action"] is None  # audit 后流程完成


# ─── kingdee_submit_bills ───────────────────────────────

class TestSubmitBills:
    @pytest.mark.asyncio
    async def test_submit_returns_ids(self):
        api_result = {
            "Result": {
                "ResponseStatus": {"IsSuccess": True, "Errors": []},
                "Ids": ["3"],
            }
        }
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_submit_bills(
                BillIdsInput(form_id="STK_InStock", bill_ids=["3"])
            )
        parsed = json.loads(result)
        assert parsed["op"] == "submit"
        assert parsed["success"] is True
        assert parsed["bill_ids"] == ["3"]
        assert parsed["next_action"] == "audit"


# ─── kingdee_unaudit_bills ─────────────────────────────

class TestUnauditBills:
    @pytest.mark.asyncio
    async def test_unaudit_returns_ids(self):
        api_result = {
            "Result": {
                "ResponseStatus": {"IsSuccess": True, "Errors": []},
                "Ids": ["1"],
            }
        }
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_unaudit_bills(
                BillIdsInput(form_id="PUR_PurchaseOrder", bill_ids=["1"])
            )
        parsed = json.loads(result)
        assert parsed["op"] == "unaudit"
        assert parsed["success"] is True
        assert parsed["bill_ids"] == ["1"]
        assert parsed["next_action"] is None  # 反审核后流程完成


# ─── kingdee_delete_bills ───────────────────────────────

class TestDeleteBills:
    @pytest.mark.asyncio
    async def test_delete_returns_ids(self):
        api_result = {
            "Result": {
                "ResponseStatus": {"IsSuccess": True, "Errors": []},
                "Ids": ["5"],
            }
        }
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_delete_bills(
                BillIdsInput(form_id="PUR_PurchaseOrder", bill_ids=["5"])
            )
        parsed = json.loads(result)
        assert parsed["op"] == "delete"
        assert parsed["success"] is True
        assert parsed["bill_ids"] == ["5"]


# ─── kingdee_push_bill ─────────────────────────────────

class TestPushBill:
    @pytest.mark.asyncio
    async def test_push_returns_generated_bill(self):
        api_result = {
            "Result": {
                "ResponseStatus": {"IsSuccess": True, "Errors": []},
                "Ids": ["300"],
                "Numbers": ["XSCKD2026030001"],
            }
        }
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_push_bill(
                PushDownInput(
                    form_id="SAL_SaleOrder",
                    target_form_id="SAL_OUTSTOCK",
                    source_bill_nos=["XSDD200"],
                )
            )
        parsed = json.loads(result)
        assert parsed["op"] == "push"
        assert parsed["success"] is True
        assert parsed["target_bill_nos"] == ["XSCKD2026030001"]
        assert parsed["next_action"] == "submit+audit"
        assert "tip" in parsed

    @pytest.mark.asyncio
    async def test_push_multiple_source_ids(self):
        api_result = {
            "Result": {
                "ResponseStatus": {"IsSuccess": True, "Errors": []},
                "Ids": ["300", "301"],
                "Numbers": ["XSCKD001", "XSCKD002"],
            }
        }
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_push_bill(
                PushDownInput(
                    form_id="SAL_SaleOrder",
                    target_form_id="SAL_OUTSTOCK",
                    source_bill_nos=["XSDD200", "XSDD201"],
                )
            )
        parsed = json.loads(result)
        assert len(parsed["target_bill_nos"]) == 2
        assert parsed["source_bill_nos"] == ["XSDD200", "XSDD201"]

    @pytest.mark.asyncio
    async def test_push_with_enable_default_rule(self):
        api_result = {
            "Result": {
                "ResponseStatus": {"IsSuccess": True, "Errors": []},
                "Ids": ["300"],
                "Numbers": ["CGRKD001"],
            }
        }
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_push_bill(
                PushDownInput(
                    form_id="PUR_PurchaseOrder",
                    target_form_id="STK_InStock",
                    source_bill_nos=["CGDD001"],
                    enable_default_rule=True,
                )
            )
            # 验证传给 Kingdee 的 body 包含 IsEnableDefaultRule
            call_args = mock_post.call_args
            assert call_args[0][0] == "push"
            assert call_args[0][1] == "PUR_PurchaseOrder"
            assert call_args[0][2]["IsEnableDefaultRule"] == "true"
            assert "RuleId" not in call_args[0][2]
        # 验证返回格式
        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["next_action"] == "submit+audit"

    @pytest.mark.asyncio
    async def test_push_with_rule_id_and_draft_on_fail(self):
        api_result = {
            "Result": {
                "ResponseStatus": {"IsSuccess": True, "Errors": []},
                "Ids": ["400"],
                "Numbers": ["CGRKD002"],
            }
        }
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = api_result
            result = await kingdee_push_bill(
                PushDownInput(
                    form_id="PUR_PurchaseOrder",
                    target_form_id="STK_InStock",
                    source_bill_nos=["CGDD002"],
                    rule_id="PUR_PurchaseOrder-STK_InStock",
                    draft_on_fail=True,
                )
            )
            call_args = mock_post.call_args
            assert call_args[0][2]["RuleId"] == "PUR_PurchaseOrder-STK_InStock"
            assert call_args[0][2]["IsDraftWhenSaveFail"] == "true"
            # rule_id 和 enable_default_rule 互斥，不应同时设置 IsEnableDefaultRule
            assert "IsEnableDefaultRule" not in call_args[0][2]
        parsed = json.loads(result)
        assert parsed["success"] is True


# ─── kingdee_create_and_audit (composite) ───────────────

def _ok_save(fid="100", bill_no="BN001"):
    return {"Result": {"ResponseStatus": {"IsSuccess": True}, "Id": fid, "Number": bill_no, "FBillNo": bill_no}}


def _ok_simple():
    return {"Result": {"ResponseStatus": {"IsSuccess": True}, "Ids": ["100"]}}


def _fail_with(message: str):
    return {"Result": {"ResponseStatus": {"IsSuccess": False, "Errors": [{"Message": message}]}}}


class TestCreateAndAudit:
    @pytest.mark.asyncio
    async def test_happy_path_three_steps(self):
        responses = [_ok_save("123", "SO123"), _ok_simple(), _ok_simple()]
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = responses
            result = await kingdee_create_and_audit(
                CreateAndAuditInput(form_id="SAL_SaleOrder", model={"FDate": "2026-04-30"})
            )
        parsed = json.loads(result)
        assert parsed["op"] == "create_and_audit"
        assert parsed["success"] is True
        assert parsed["halted_at"] is None
        assert len(parsed["steps"]) == 3
        assert [s["op"] for s in parsed["steps"]] == ["save", "submit", "audit"]
        assert all(s["success"] for s in parsed["steps"])
        assert parsed["fid"] == "123"
        assert parsed["bill_no"] == "SO123"
        assert parsed["next_action"] is None
        assert mock_post.await_count == 3

    @pytest.mark.asyncio
    async def test_halt_at_save(self):
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _fail_with("FCustId 不能为空")
            result = await kingdee_create_and_audit(
                CreateAndAuditInput(form_id="SAL_SaleOrder", model={})
            )
            assert mock_post.await_count == 1  # 不会继续 submit
        parsed = json.loads(result)
        assert parsed["success"] is False
        assert parsed["halted_at"] == "save"
        assert "recovery_hint" in parsed
        # next_action_tool 应通过模式匹配带出
        assert any(
            e.get("matched", {}).get("next_action_tool") == "kingdee_get_fields"
            for e in parsed["errors"]
        )

    @pytest.mark.asyncio
    async def test_halt_at_submit_carries_fid(self):
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [_ok_save("999", "SO999"), _fail_with("非草稿状态")]
            result = await kingdee_create_and_audit(
                CreateAndAuditInput(form_id="SAL_SaleOrder", model={})
            )
            assert mock_post.await_count == 2
        parsed = json.loads(result)
        assert parsed["halted_at"] == "submit"
        assert parsed["fid"] == "999"
        assert "999" in parsed["recovery_hint"]
        assert "kingdee_submit_bills" in parsed["recovery_hint"]

    @pytest.mark.asyncio
    async def test_halt_at_audit_carries_fid(self):
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [
                _ok_save("777", "SO777"),
                _ok_simple(),
                _fail_with("基础资料不存在"),
            ]
            result = await kingdee_create_and_audit(
                CreateAndAuditInput(form_id="SAL_SaleOrder", model={})
            )
            assert mock_post.await_count == 3
        parsed = json.loads(result)
        assert parsed["halted_at"] == "audit"
        assert parsed["fid"] == "777"
        assert "kingdee_audit_bills" in parsed["recovery_hint"]


class TestPushAndAudit:
    @pytest.mark.asyncio
    async def test_happy_path_push_submit_audit(self):
        push_resp = {
            "Result": {
                "ResponseStatus": {"IsSuccess": True},
                "Numbers": ["RB001"],
                "Ids": ["555"],
            }
        }
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [push_resp, _ok_simple(), _ok_simple()]
            result = await kingdee_push_and_audit(
                PushAndAuditInput(
                    form_id="PUR_PurchaseOrder",
                    target_form_id="PUR_ReceiveBill",
                    source_bill_nos=["CGDD001"],
                    rule_id="PUR_PurchaseOrder-PUR_ReceiveBill",
                )
            )
        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["halted_at"] is None
        assert parsed["target_bill_nos"] == ["RB001"]
        assert parsed["target_fids"] == ["555"]
        assert [s["op"] for s in parsed["steps"]] == ["push", "submit", "audit"]

    @pytest.mark.asyncio
    async def test_auto_submit_audit_false_stops_after_push(self):
        push_resp = {
            "Result": {
                "ResponseStatus": {"IsSuccess": True},
                "Numbers": ["RB002"],
                "Ids": ["556"],
            }
        }
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = push_resp
            result = await kingdee_push_and_audit(
                PushAndAuditInput(
                    form_id="PUR_PurchaseOrder",
                    target_form_id="PUR_ReceiveBill",
                    source_bill_nos=["CGDD002"],
                    rule_id="x",
                    auto_submit_audit=False,
                )
            )
            assert mock_post.await_count == 1
        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["next_action"] == "submit+audit"
        assert len(parsed["steps"]) == 1

    @pytest.mark.asyncio
    async def test_push_failure_includes_matched_pattern(self):
        with patch("kingdee_mcp.server._post_raw", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _fail_with("源单关联数量已达上限")
            result = await kingdee_push_and_audit(
                PushAndAuditInput(
                    form_id="PUR_PurchaseOrder",
                    target_form_id="PUR_ReceiveBill",
                    source_bill_nos=["CGDD003"],
                    rule_id="x",
                )
            )
            assert mock_post.await_count == 1
        parsed = json.loads(result)
        assert parsed["halted_at"] == "push"
        assert any(
            e.get("matched", {}).get("next_action_tool") == "kingdee_query_purchase_order_progress"
            for e in parsed["errors"]
        )
