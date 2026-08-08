"""批量 Ids 不得静默丢单 —— issue #8 防回归测试

背景（issue #8，2026-05-11 真机复现）：
    `_post_raw` 在处理 submit/audit/unaudit/delete 时，遇到 list 形式的 Ids
    直接取 `ids[0]`，其余 ID **静默丢弃**，接口仍返回 `success: true`。
    用户传 11 张单据反审核，实际只有 1 张生效，另外 10 张原封不动；
    整批 46 张单据只处理了 6 张（每类首条），漏掉 87%。

    这类「假成功」比直接报错危险得多 —— 调用方（尤其是 AI Agent）看到
    success 就会继续往下走，错误一路扩散到后续单据流程。

本测试锁死两条底线：
    1. 多个 ID 必须全部发给金蝶（逗号拼接），一个都不能丢。
    2. 金蝶少处理了单据时，success 必须为 False，不许报"假成功"。

两条都是纯函数级校验，不需要连真机账套，可以永久防住这类回归。
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kingdee_mcp.server import _normalize_ids, _reconcile_batch, _result_status


# ─── 底线一：多个 ID 一个都不能丢 ──────────────────────────

class TestNormalizeIds:
    def test_issue_8_original_case_all_11_ids_survive(self):
        """issue #8 原始复现场景：11 个 ID 必须全部发出去。"""
        ids = ["100155", "100154", "100153", "100152", "100151", "100150",
               "100149", "100148", "100147", "100146", "100145"]
        out = _normalize_ids(ids, ep_key="unaudit")

        assert out.count(",") == 10, "逗号数量不对，说明有 ID 被吞了"
        for bill_id in ids:
            assert bill_id in out.split(","), f"{bill_id} 被静默丢弃（issue #8 回归）"

    def test_list_is_comma_joined_not_truncated(self):
        """核心回归点：list 必须逗号拼接，绝不能退化成 ids[0]。"""
        out = _normalize_ids(["1", "2", "3"], ep_key="delete")
        assert out == "1,2,3"
        assert out != "1", "又退回到只取首个 ID 的老 bug 了"

    def test_single_string_unchanged(self):
        """单个字符串保持原样，不能被改写。"""
        assert _normalize_ids("100155", ep_key="submit") == "100155"

    def test_tuple_and_int_supported(self):
        """元组与整型 ID 同样要完整保留。"""
        assert _normalize_ids((1, 2, 3), ep_key="audit") == "1,2,3"
        assert _normalize_ids(100155, ep_key="audit") == "100155"

    def test_whitespace_stripped_and_blanks_dropped(self):
        """空白项剔除，但有效 ID 一个不少。"""
        assert _normalize_ids([" 1 ", "", "  ", "2"], ep_key="submit") == "1,2"

    def test_duplicates_removed_order_preserved(self):
        """重复 ID 去重，且保持调用方给的顺序。"""
        assert _normalize_ids(["3", "1", "3", "2", "1"], ep_key="submit") == "3,1,2"

    @pytest.mark.parametrize("empty", [[], (), "", "   ", ["", "  "]])
    def test_empty_raises_instead_of_sending_blank(self, empty):
        """空 ID 必须显式报错，不许悄悄发一个空 Ids 上去。"""
        with pytest.raises(ValueError):
            _normalize_ids(empty, ep_key="delete")


# ─── 底线二：少处理了就不许报成功 ──────────────────────────

def _kingdee_response(success_ids, is_success=True):
    """构造金蝶 WebAPI 的批量操作返回。"""
    return {
        "Result": {
            "ResponseStatus": {
                "IsSuccess": is_success,
                "Errors": [],
                "SuccessEntitys": [
                    {"Id": int(i), "Number": f"BILL{i}", "DIndex": n}
                    for n, i in enumerate(success_ids)
                ],
            }
        }
    }


class TestReconcileBatch:
    def test_partial_success_is_reported_as_failure(self):
        """issue #8 的假成功场景：提交 11 张只成功 1 张，success 必须是 False。"""
        requested = [str(100145 + i) for i in range(11)]
        resp = _kingdee_response(["100155"])

        out = _result_status(resp, "unaudit", requested_ids=requested)

        assert out["success"] is False, "金蝶只处理了 1/11 却报成功 —— issue #8 回归"
        assert out["requested_count"] == 11
        assert out["succeeded_count"] == 1
        assert len(out["missing_ids"]) == 10
        assert "100155" not in out["missing_ids"]

    def test_full_success_stays_successful(self):
        """全部成功时不能误伤，success 保持 True。"""
        requested = ["1", "2", "3"]
        out = _result_status(_kingdee_response(requested), "submit", requested_ids=requested)

        assert out["success"] is True
        assert out["succeeded_count"] == 3
        assert "missing_ids" not in out

    def test_missing_ids_listed_explicitly(self):
        """漏掉的单据要点名列出，方便调用方补做。"""
        out = _result_status(_kingdee_response(["1", "3"]), "audit",
                             requested_ids=["1", "2", "3", "4"])

        assert out["missing_ids"] == ["2", "4"]
        assert "missing_ids" in out.get("tip", "") or out["missing_ids"]

    def test_no_requested_ids_keeps_legacy_behaviour(self):
        """不传 requested_ids 时行为完全不变，保证老调用方零影响。"""
        out = _result_status(_kingdee_response(["1"]), "submit")

        assert out["success"] is True
        assert "requested_count" not in out
        assert "missing_ids" not in out

    def test_reconcile_skips_when_response_unparseable(self):
        """金蝶没返回 SuccessEntitys 时无法对账，退回原逻辑而不是误判失败。"""
        resp = {"Result": {"ResponseStatus": {"IsSuccess": True, "Errors": []}}}
        out = _result_status(resp, "submit", requested_ids=["1", "2"])

        assert out["success"] is True
        assert _reconcile_batch(resp["Result"]["ResponseStatus"], ["1", "2"]) == {}

    def test_comma_string_requested_ids_supported(self):
        """requested_ids 传逗号字符串也要能对账。"""
        out = _result_status(_kingdee_response(["1"]), "delete", requested_ids="1,2,3")

        assert out["success"] is False
        assert out["missing_ids"] == ["2", "3"]
