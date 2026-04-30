"""
Kingdee MCP Server 基础测试（mock 模式，无需真实金蝶服务器）
"""

import json
import asyncio
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from pydantic import ValidationError

# 导入待测模块（路径适配）
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kingdee_mcp.server import (
    _query_payload, _rows, _err, _fmt,
    _match_known_pattern, _parse_kingdee_errors, add_known_pattern,
    KNOWN_ERROR_NEXT_ACTIONS,
    QueryInput, ViewInput, SaveInput, BillIdsInput,
    MaterialQueryInput, PartnerQueryInput, InventoryQueryInput,
    FormSearchInput, FieldQueryInput,
    kingdee_list_forms, kingdee_get_fields,
)


# ─── Pydantic 模型验证测试 ───────────────────────────────

class TestPydanticModels:
    def test_query_input_defaults(self):
        p = QueryInput(form_id="PUR_PurchaseOrder")
        assert p.form_id == "PUR_PurchaseOrder"
        assert p.limit == 20
        assert p.start_row == 0

    def test_query_input_custom_limit(self):
        p = QueryInput(form_id="SAL_SaleOrder", limit=50)
        assert p.limit == 50

    def test_query_input_rejects_extra(self):
        with pytest.raises(ValidationError):
            QueryInput(form_id="PUR_PurchaseOrder", unknown_field=123)

    def test_view_input_requires_fields(self):
        p = ViewInput(form_id="PUR_PurchaseOrder", bill_id="12345")
        assert p.bill_id == "12345"

    def test_save_input_model_required(self):
        p = SaveInput(form_id="PUR_PurchaseOrder", model={"FDate": "2024-01-01"})
        assert p.model["FDate"] == "2024-01-01"

    def test_bill_ids_requires_list(self):
        with pytest.raises(ValidationError):
            BillIdsInput(form_id="PUR_PurchaseOrder", bill_ids=[])  # min_length=1

    def test_bill_ids_min_length(self):
        p = BillIdsInput(form_id="PUR_PurchaseOrder", bill_ids=["123"])
        assert len(p.bill_ids) == 1

    def test_inventory_query_input_default_filter(self):
        p = InventoryQueryInput()
        assert p.filter_string == "FBaseQty>0"

    def test_partner_query_input_partner_type(self):
        p = PartnerQueryInput(partner_type="BD_Customer")
        assert p.partner_type == "BD_Customer"


# ─── 工具函数测试 ───────────────────────────────────────

class TestUtilityFunctions:
    def test_query_payload_format(self):
        payload = _query_payload(
            "PUR_PurchaseOrder",
            "FID,FBillNo",
            "FDocumentStatus='C'",
            "FDate DESC",
            0, 20
        )
        assert payload["FormId"] == "PUR_PurchaseOrder"
        assert payload["FieldKeys"] == "FID,FBillNo"
        assert payload["Limit"] == 20
        assert payload["StartRow"] == 0

    def test_rows_with_list(self):
        assert _rows([1, 2, 3]) == [1, 2, 3]

    def test_rows_with_result_key(self):
        assert _rows({"Result": [1, 2]}) == [1, 2]

    def test_rows_with_data_key(self):
        assert _rows({"data": [1, 2]}) == [1, 2]

    def test_rows_with_unknown_key(self):
        # 未知 key 返回空列表（fallback 到空列表）
        assert _rows({"unknown": [1, 2]}) == []

    def test_fmt_json_output(self):
        result = _fmt({"key": "value"})
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_err_httpx_status(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        err = _err(httpx.HTTPStatusError("fail", request=MagicMock(), response=mock_resp))
        assert "认证失败" in err  # 401 有专门的错误提示

    def test_err_timeout(self):
        err = _err(httpx.TimeoutException("timeout"))
        assert "超时" in err


# ─── 元数据工具测试 ─────────────────────────────────────

class TestMetadataTools:
    def test_kingdee_list_forms_returns_all(self):
        result = asyncio.run(kingdee_list_forms(FormSearchInput(keyword="")))
        parsed = json.loads(result)
        # 应返回所有 FORM_CATALOG 中的表单
        assert parsed["count"] > 0
        assert len(parsed["forms"]) == parsed["count"]
        # 验证新增字段
        first_form = parsed["forms"][0]
        assert "alias" in first_form
        assert "desc" in first_form
        assert "db_tables" in first_form
        assert "has_business_rules" in first_form

    def test_kingdee_list_forms_filter_by_keyword(self):
        result = asyncio.run(kingdee_list_forms(FormSearchInput(keyword="采购")))
        parsed = json.loads(result)
        for form in parsed["forms"]:
            name_lower = form["name"].lower()
            alias_lower = [a.lower() for a in form["alias"]]
            assert "采购" in name_lower or any("采购" in a for a in alias_lower)

    def test_kingdee_get_fields_known_form(self):
        result = asyncio.run(kingdee_get_fields(FieldQueryInput(form_id="BD_Material")))
        parsed = json.loads(result)
        assert parsed["form_id"] == "BD_Material"
        assert parsed["name"] == "物料"
        assert "recommended_fields" in parsed
        assert "db_tables" in parsed
        assert "business_rules" in parsed
        assert "单据状态枚举" in parsed

    def test_kingdee_get_fields_unknown_form(self):
        result = asyncio.run(kingdee_get_fields(FieldQueryInput(form_id="UNKNOWN_FORM")))
        parsed = json.loads(result)
        assert parsed["form_id"] == "UNKNOWN_FORM"
        assert parsed["name"] == "未知表单"
        assert "common_fields" in parsed


# ─── 错误模式匹配 + next-action ───────────────────────────────

class TestErrorPatternMatching:
    def test_match_known_pattern_returns_none_for_unmatched(self):
        assert _match_known_pattern("totally novel error") is None

    def test_match_known_pattern_returns_reason_and_suggestion(self):
        m = _match_known_pattern("分录行已冻结，不允许编辑")
        assert m is not None
        assert "冻结" in m["reason"] or "冻结" in m["suggestion"]

    def test_match_known_pattern_includes_next_action_when_registered(self):
        m = _match_known_pattern("FQty 字段不存在于本账套")
        assert m is not None
        assert m["next_action_tool"] == "kingdee_get_fields"
        assert m["next_action_args_hint"] == "form_id"

    def test_match_known_pattern_no_next_action_for_simple_match(self):
        # 业务关闭 没有注册 next-action，只有 reason/suggestion
        m = _match_known_pattern("该行已业务关闭")
        assert m is not None
        assert "next_action_tool" not in m

    def test_parse_errors_top_level_response_status(self):
        result = {
            "Result": {
                "ResponseStatus": {
                    "IsSuccess": False,
                    "Errors": [{"Message": "FCustId 不能为空", "FieldName": "FCustId"}],
                }
            }
        }
        errors = _parse_kingdee_errors(result)
        assert len(errors) == 1
        assert errors[0]["matched"]["next_action_tool"] == "kingdee_get_fields"
        assert errors[0]["field"] == "FCustId"

    def test_parse_errors_convert_response_status_gets_matched(self):
        # push 逐行失败必须也走 pattern 匹配（这是改动的核心）
        result = {
            "Result": {
                "ResponseStatus": {"IsSuccess": True},
                "ConvertResponseStatus": [
                    {"IsSuccess": False, "Message": "源单关联数量已达上限", "Description": "row 0"},
                    {"IsSuccess": True},
                ],
            }
        }
        errors = _parse_kingdee_errors(result)
        assert len(errors) == 1
        assert errors[0]["type"] == "convert"
        assert errors[0]["row"] == 0
        assert errors[0]["matched"] is not None
        assert errors[0]["matched"]["next_action_tool"] == "kingdee_query_purchase_order_progress"

    def test_parse_errors_dedupes_repeat_message(self):
        # 顶层 + convert 中的同一条 message 不应重复出现
        result = {
            "Result": {
                "ResponseStatus": {
                    "IsSuccess": False,
                    "Errors": [{"Message": "已审核单据，不允许操作"}],
                },
                "ConvertResponseStatus": [
                    {"IsSuccess": False, "Message": "其他错误"},
                ],
            }
        }
        errors = _parse_kingdee_errors(result)
        # 顶层 1 条 + convert 1 条（不同 message） = 2 条
        assert len(errors) == 2

    def test_add_known_pattern_with_next_action(self):
        add_known_pattern(
            "测试新模式xyz",
            "test reason",
            "test suggestion",
            next_action_tool="kingdee_view_bill",
            next_action_args_hint="form_id, bill_id",
        )
        m = _match_known_pattern("出现了 测试新模式xyz")
        assert m is not None
        assert m["next_action_tool"] == "kingdee_view_bill"

    def test_add_known_pattern_three_arg_still_works(self):
        # 向后兼容：三参签名继续可用
        add_known_pattern("旧式三参pattern", "reason", "suggestion")
        m = _match_known_pattern("出现了 旧式三参pattern")
        assert m is not None
        assert "next_action_tool" not in m
