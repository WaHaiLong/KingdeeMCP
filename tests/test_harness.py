"""
Harness 约束层单元测试
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from harness.rules import (
    OpNode, HARNESS_RULES, validate_operation_chain, HarnessRule
)
from harness.feedback_loop import generate_loop_hint, FeedbackLoop


class TestHarnessRules:
    """Harness 约束规则测试"""

    def test_rule_001_incomplete_lifecycle(self):
        """RULE-001: save 后没有 submit，应检测到违规"""
        nodes = [
            OpNode(
                tool="kingdee_save_bill",
                params={"form_id": "PUR_PurchaseOrder", "model": {}},
                result={"op": "save", "success": True, "fid": "100001", "next_action": "submit"},
                timestamp=1.0,
            ),
        ]
        violations = validate_operation_chain(nodes)
        error_rules = [v for v in violations if v["severity"] == "error"]
        assert any(v["rule_id"] == "RULE-001" for v in error_rules), "应检测到生命周期不完整"

    def test_rule_001_complete_lifecycle(self):
        """RULE-001: save → submit → audit，应通过"""
        nodes = [
            OpNode(
                tool="kingdee_save_bill",
                params={"form_id": "PUR_PurchaseOrder", "model": {}},
                result={"op": "save", "success": True, "fid": "100001", "next_action": "submit"},
                timestamp=1.0,
            ),
            OpNode(
                tool="kingdee_submit_bills",
                params={"form_id": "PUR_PurchaseOrder", "bill_ids": ["100001"]},
                result={"op": "submit", "success": True, "fid": "100001", "next_action": "audit"},
                timestamp=2.0,
            ),
            OpNode(
                tool="kingdee_audit_bills",
                params={"form_id": "PUR_PurchaseOrder", "bill_ids": ["100001"]},
                result={"op": "audit", "success": True, "fid": "100001", "next_action": None},
                timestamp=3.0,
            ),
        ]
        violations = validate_operation_chain(nodes)
        error_rules = [v for v in violations if v["severity"] == "error"]
        assert len(error_rules) == 0, "完整生命周期应通过 RULE-001"

    def test_rule_002_push_incomplete(self):
        """RULE-002: push 后没有 submit+audit，应检测到违规"""
        nodes = [
            OpNode(
                tool="kingdee_push_bill",
                params={"form_id": "PUR_PurchaseOrder", "target_form_id": "STK_InStock", "source_bill_nos": ["CGDD001"]},
                result={"op": "push", "success": True, "target_bill_nos": ["CGRKD001"], "next_action": "submit+audit"},
                timestamp=1.0,
            ),
        ]
        violations = validate_operation_chain(nodes)
        error_rules = [v for v in violations if v["severity"] == "error"]
        assert any(v["rule_id"] == "RULE-002" for v in error_rules), "应检测到 Push 操作链不完整"

    def test_rule_002_push_complete(self):
        """RULE-002: push → submit → audit，应通过"""
        nodes = [
            OpNode(
                tool="kingdee_push_bill",
                params={"form_id": "PUR_PurchaseOrder", "target_form_id": "STK_InStock", "source_bill_nos": ["CGDD001"]},
                result={"op": "push", "success": True, "target_bill_nos": ["CGRKD001"], "next_action": "submit+audit"},
                timestamp=1.0,
            ),
            OpNode(
                tool="kingdee_submit_bills",
                params={"form_id": "STK_InStock", "bill_ids": ["300001"]},
                result={"op": "submit", "success": True, "fid": "300001", "next_action": "audit"},
                timestamp=2.0,
            ),
            OpNode(
                tool="kingdee_audit_bills",
                params={"form_id": "STK_InStock", "bill_ids": ["300001"]},
                result={"op": "audit", "success": True, "fid": "300001", "next_action": None},
                timestamp=3.0,
            ),
        ]
        violations = validate_operation_chain(nodes)
        error_rules = [v for v in violations if v["severity"] == "error"]
        assert len(error_rules) == 0, "完整 Push 流程应通过"

    def test_rule_003_error_no_recovery(self):
        """RULE-003: 操作失败且是最后一个，应检测到无修正"""
        nodes = [
            OpNode(
                tool="kingdee_save_bill",
                params={"form_id": "PUR_PurchaseOrder", "model": {}},
                result={"op": "save", "success": False, "errors": [{"message": "测试错误"}]},
                timestamp=1.0,
            ),
        ]
        violations = validate_operation_chain(nodes)
        error_rules = [v for v in violations if v["severity"] == "error"]
        assert any(v["rule_id"] == "RULE-003" for v in error_rules), "应检测到无修正动作"

    def test_rule_003_error_with_recovery(self):
        """RULE-003: 操作失败后有修正动作，应通过"""
        nodes = [
            OpNode(
                tool="kingdee_save_bill",
                params={"form_id": "PUR_PurchaseOrder", "model": {}},
                result={"op": "save", "success": False, "errors": [{"message": "测试错误"}]},
                timestamp=1.0,
            ),
            OpNode(
                tool="kingdee_view_bill",
                params={"form_id": "PUR_PurchaseOrder", "bill_id": "100001"},
                result={"op": "view", "success": True, "data": {}},
                timestamp=2.0,
            ),
        ]
        violations = validate_operation_chain(nodes)
        error_rules = [v for v in violations if v["severity"] == "error"]
        assert len(error_rules) == 0, "有修正动作应通过 RULE-003"

    def test_rule_004_duplicate_query(self):
        """RULE-004: 连续相同查询应检测到无效重复"""
        nodes = [
            OpNode(
                tool="kingdee_query_bills",
                params={"form_id": "PUR_PurchaseOrder", "filter_string": "FDocumentStatus='C'"},
                result={"op": "query", "success": True, "count": 5, "data": [1, 2, 3]},
                timestamp=1.0,
            ),
            OpNode(
                tool="kingdee_query_bills",
                params={"form_id": "PUR_PurchaseOrder", "filter_string": "FDocumentStatus='C'"},
                result={"op": "query", "success": True, "count": 5, "data": [1, 2, 3]},
                timestamp=2.0,
            ),
        ]
        violations = validate_operation_chain(nodes)
        warning_rules = [v for v in violations if v["severity"] == "warning"]
        assert any(v["rule_id"] == "RULE-004" for v in warning_rules), "应检测到无效重复查询"


class TestFeedbackLoop:
    """反馈循环测试"""

    def test_generate_loop_hint_success_with_next_action(self):
        """操作成功且有 next_action 时，生成 submit 引导"""
        result = {"op": "save", "success": True, "fid": "100001", "next_action": "submit"}
        hint = generate_loop_hint("save", result)
        assert hint["status"] == "ok"
        assert hint["phase"] == "awaiting_audit"
        assert "kingdee_submit_bills" in str(hint["actions"]["if_ok"])

    def test_generate_loop_hint_success_complete(self):
        """操作成功且无 next_action 时，phase=complete"""
        result = {"op": "audit", "success": True, "fid": "100001", "next_action": None}
        hint = generate_loop_hint("audit", result)
        assert hint["status"] == "ok"
        assert hint["phase"] == "complete"

    def test_generate_loop_hint_error(self):
        """操作失败时，生成 recover 分支"""
        result = {
            "op": "save",
            "success": False,
            "errors": [
                {"type": "http", "code": 500, "message": "服务器错误"}
            ]
        }
        hint = generate_loop_hint("save", result)
        assert hint["status"] == "error"
        assert hint["phase"] == "recover"
        assert len(hint["errors"]) == 1

    def test_feedback_loop_tracker(self):
        """FeedbackLoop 追踪器记录操作并生成 hint"""
        tracker = FeedbackLoop()
        hint1 = tracker.record("save", {"form_id": "PUR_PurchaseOrder"}, {"success": True, "fid": "100001", "next_action": "submit"})
        hint2 = tracker.record("submit", {"bill_ids": ["100001"]}, {"success": True, "fid": "100001", "next_action": "audit"})
        hint3 = tracker.record("audit", {"bill_ids": ["100001"]}, {"success": True, "fid": "100001", "next_action": None})

        summary = tracker.summary()
        assert summary["total_operations"] == 3
        assert summary["complete"] == True
        assert summary["error_count"] == 0

        violations = tracker.check_violations()
        error_rules = [v for v in violations if v["severity"] == "error"]
        assert len(error_rules) == 0, "完整流程不应有违规"


class TestOpNode:
    """OpNode 工具类测试"""

    def test_op_node_success(self):
        node = OpNode(
            tool="kingdee_save_bill",
            params={"form_id": "PUR_PurchaseOrder"},
            result={"success": True, "fid": "100001"},
            timestamp=1.0,
        )
        assert node.is_success == True
        assert node.next_action is None
        assert node.fid == "100001"

    def test_op_node_with_bill_ids(self):
        node = OpNode(
            tool="kingdee_submit_bills",
            params={"bill_ids": ["100001", "100002"]},
            result={"success": True, "bill_ids": ["100001", "100002"]},
            timestamp=1.0,
        )
        assert node.bill_ids == ["100001", "100002"]

    def test_op_node_with_errors(self):
        node = OpNode(
            tool="kingdee_save_bill",
            params={},
            result={"success": False, "errors": [{"message": "error"}]},
            timestamp=1.0,
        )
        assert node.is_success == False