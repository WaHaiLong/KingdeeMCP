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

    def test_kingdee_list_forms_filter_by_keyword(self):
        result = asyncio.run(kingdee_list_forms(FormSearchInput(keyword="采购")))
        parsed = json.loads(result)
        for form in parsed["forms"]:
            name_lower = form["name"].lower()
            keywords_lower = [k.lower() for k in form["keywords"]]
            assert "采购" in name_lower or any("采购" in k for k in keywords_lower)

    def test_kingdee_get_fields_known_form(self):
        result = asyncio.run(kingdee_get_fields(FieldQueryInput(form_id="BD_Material")))
        parsed = json.loads(result)
        assert parsed["form_id"] == "BD_Material"
        assert parsed["name"] == "物料"
        assert "recommended_fields" in parsed

    def test_kingdee_get_fields_unknown_form(self):
        result = asyncio.run(kingdee_get_fields(FieldQueryInput(form_id="UNKNOWN_FORM")))
        parsed = json.loads(result)
        assert parsed["form_id"] == "UNKNOWN_FORM"
        assert parsed["name"] == "未知表单"
        assert "common_fields" in parsed
