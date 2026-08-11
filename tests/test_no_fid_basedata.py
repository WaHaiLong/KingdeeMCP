"""
issue #28 回归测试：无 FID 视图的基础资料查询

覆盖点：
1. 根因 —— QueryInput.order_string 默认 "FID DESC" 会把 FID 注入 SQL，
   所以「field_keys 不含 FID 仍报 列名 'FID' 无效」。修复后已知表单不得再发出 FID。
2. 已知名单（BD_Currency/BD_AccountBook/BD_VOUCHERGROUP/BD_RateType）走前置降级，
   一次请求搞定，不浪费一次往返。
3. 未知表单撞错误 → 自动去 FID 重试一次并学习，同进程第二次直接降级。
4. 普通单据（PUR_PurchaseOrder）行为不变，FID 照常带上，避免回归。
5. 重试后仍失败 → 返回人话提示，不把底层 SQL 报错甩给用户。
"""

import json
import pytest
from unittest.mock import patch, AsyncMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kingdee_mcp import server
from kingdee_mcp.server import (
    kingdee_query_bills, QueryInput,
    NO_FID_FORMS, _strip_fid, _is_no_fid_error, _form_lacks_fid,
)

# 金蝶在这种情况下的真实报错形状（取自 issue #28）
NO_FID_ERROR = {
    "Result": {
        "ResponseStatus": {
            "IsSuccess": False,
            "Errors": [{"Message": "列名 'FID' 无效。"}],
        }
    }
}

OK_ROWS = {"Result": [{"FNumber": "PRE001", "FName": "人民币"}]}


@pytest.fixture(autouse=True)
def _clear_learned():
    """每个用例前后清空运行时学习集，防止用例间互相污染"""
    server._LEARNED_NO_FID_FORMS.clear()
    yield
    server._LEARNED_NO_FID_FORMS.clear()


# ─── 纯函数层 ───────────────────────────────────────────

class TestStripFid:
    def test_removes_bare_fid_from_fields_and_order(self):
        fk, od = _strip_fid("FID,FNumber,FName", "FID DESC")
        assert fk == "FNumber,FName"
        assert od == "FNumber ASC"          # 空排序回退，别发空串

    def test_keeps_prefixed_fields(self):
        """FSupplierId.FNumber / FIDX 不是裸 FID，不能被误删"""
        fk, _ = _strip_fid("FID,FIDX,FSupplierId.FNumber", "FID DESC")
        assert fk == "FIDX,FSupplierId.FNumber"

    def test_keeps_other_order_terms(self):
        _, od = _strip_fid("FNumber", "FID DESC, FNumber ASC")
        assert od == "FNumber ASC"

    def test_empty_fields_fall_back(self):
        fk, od = _strip_fid("FID", "FID DESC")
        assert fk == "FNumber,FName" and od == "FNumber ASC"


class TestErrorDetection:
    def test_detects_chinese_error(self):
        assert _is_no_fid_error(NO_FID_ERROR) is True

    def test_detects_english_error(self):
        assert _is_no_fid_error(
            {"Result": {"ResponseStatus": {"Errors": [
                {"Message": "Invalid column name 'FID'."}]}}}
        ) is True

    def test_normal_rows_not_flagged(self):
        assert _is_no_fid_error(OK_ROWS) is False


class TestWhitelist:
    @pytest.mark.parametrize("form_id", [
        "BD_Currency", "BD_AccountBook", "BD_VOUCHERGROUP", "BD_RateType",
    ])
    def test_issue_28_forms_are_listed(self, form_id):
        assert form_id.upper() in NO_FID_FORMS
        assert _form_lacks_fid(form_id) is True     # 大小写不敏感

    def test_normal_bill_not_listed(self):
        assert _form_lacks_fid("PUR_PurchaseOrder") is False


# ─── 工具层 ─────────────────────────────────────────────

class TestQueryBillsNoFid:
    @pytest.mark.asyncio
    async def test_known_form_never_sends_fid(self):
        """核心断言：默认 order_string='FID DESC' 也不能把 FID 发出去"""
        with patch("kingdee_mcp.server._post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = OK_ROWS
            out = json.loads(await kingdee_query_bills(
                QueryInput(form_id="BD_Currency", field_keys="FNumber,FName")
            ))

        assert mock_post.call_count == 1, "已知表单应一次成功，不该多跑一趟"
        payload = mock_post.call_args[0][1]
        assert "FID" not in payload["FieldKeys"]
        assert "FID" not in payload["OrderString"]
        assert out["count"] == 1
        assert "notice" in out and "FID" in out["notice"]

    @pytest.mark.asyncio
    async def test_known_form_with_default_fields(self):
        """连 field_keys 都用默认值（含 FID）时同样要被剥掉"""
        with patch("kingdee_mcp.server._post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = OK_ROWS
            await kingdee_query_bills(QueryInput(form_id="BD_VOUCHERGROUP"))

        payload = mock_post.call_args[0][1]
        assert "FID" not in payload["FieldKeys"].upper().split(",")
        assert not payload["OrderString"].upper().startswith("FID")

    @pytest.mark.asyncio
    async def test_unknown_form_retries_and_learns(self):
        with patch("kingdee_mcp.server._post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [NO_FID_ERROR, OK_ROWS]
            out = json.loads(await kingdee_query_bills(
                QueryInput(form_id="BD_SomeNewBaseData")
            ))

        assert mock_post.call_count == 2, "首次原样发，失败后去 FID 重试一次"
        first, second = mock_post.call_args_list
        assert "FID" in first[0][1]["OrderString"]
        assert "FID" not in second[0][1]["OrderString"]
        assert out["count"] == 1 and "notice" in out
        # 学习生效：同进程再查一次应直接降级
        assert _form_lacks_fid("BD_SomeNewBaseData") is True

        with patch("kingdee_mcp.server._post", new_callable=AsyncMock) as mock2:
            mock2.return_value = OK_ROWS
            await kingdee_query_bills(QueryInput(form_id="BD_SomeNewBaseData"))
        assert mock2.call_count == 1, "学过一次后不该再白跑"

    @pytest.mark.asyncio
    async def test_normal_bill_unchanged(self):
        """防回归：普通单据必须还带 FID，排序也不动"""
        with patch("kingdee_mcp.server._post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"Result": [{"FID": "1", "FBillNo": "PO001"}]}
            out = json.loads(await kingdee_query_bills(
                QueryInput(form_id="PUR_PurchaseOrder")
            ))

        assert mock_post.call_count == 1
        payload = mock_post.call_args[0][1]
        assert "FID" in payload["FieldKeys"]
        assert payload["OrderString"] == "FID DESC"
        assert "notice" not in out

    @pytest.mark.asyncio
    async def test_still_failing_gives_human_hint(self):
        """去 FID 后依旧报错 → 给人话，不甩 SQL 报错"""
        with patch("kingdee_mcp.server._post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = NO_FID_ERROR
            out = json.loads(await kingdee_query_bills(
                QueryInput(form_id="BD_Currency")
            ))

        assert "notice" in out
        assert "手动填入" in out["notice"] or "不支持自动查询" in out["notice"]


class TestErrorPrefilterIsCheap:
    """正常查询不该为了找错误字符串而全量序列化整份结果"""

    def test_row_array_short_circuits(self):
        from kingdee_mcp.server import _looks_like_error
        assert _looks_like_error([{"FNumber": "M001"}]) is False
        assert _looks_like_error({"Result": [{"FNumber": "M001"}]}) is False

    def test_error_shapes_pass_prefilter(self):
        from kingdee_mcp.server import _looks_like_error
        assert _looks_like_error(NO_FID_ERROR) is True
        assert _looks_like_error([{"Result": {"ResponseStatus": {"Errors": []}}}]) is True

    def test_prefilter_blocks_serialization(self, monkeypatch):
        """行数据里恰好含 FID 字样也不能被误判成错误"""
        calls = []
        real_dumps = json.dumps

        def spy(*a, **kw):
            calls.append(1)
            return real_dumps(*a, **kw)

        monkeypatch.setattr(server.json, "dumps", spy)
        assert _is_no_fid_error({"Result": [{"FID": "1", "FName": "列名 'FID' 无效"}]}) is False
        assert not calls, "正常行数组不该走到序列化"
