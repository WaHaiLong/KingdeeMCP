"""
Harness 约束层 - 操作链完整性规则

定义金蝶 MCP 操作之间的依赖关系和约束规则。
这些规则通过 check_harness.py 自动化检查，在 CI 中强制阻断不合规的操作链。

核心原则：
- 所有写操作必须走完完整生命周期（Save→Submit→Audit）
- next_action 不为 null 时，AI 不应终止工作
- Push 操作后必须紧跟 Submit + Audit
- 错误返回后必须有后续修正动作
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HarnessRule:
    """单条约束规则"""
    id: str                     # 规则唯一标识，如 "NO_TERMINATE_AFTER_SAVE"
    name: str                   # 人类可读名称
    description: str            # 规则说明
    severity: str              # "error" | "warning" | "info"
    check: callable             # 检查函数，输入操作历史，返回 (violated: bool, message: str)


# ─────────────────────────────────────────────
# 操作节点定义
# ─────────────────────────────────────────────

class OpNode:
    """操作链中的单个节点"""
    def __init__(self, tool: str, params: dict, result: dict, timestamp: float = 0):
        self.tool = tool
        self.params = params
        self.result = result
        self.timestamp = timestamp

    @property
    def is_success(self) -> bool:
        return self.result.get("success", False)

    @property
    def next_action(self) -> Optional[str]:
        return self.result.get("next_action")

    @property
    def fid(self) -> Optional[str]:
        return self.result.get("fid") or self.result.get("bill_id")

    @property
    def bill_ids(self) -> list:
        ids = self.result.get("bill_ids") or self.result.get("ids") or []
        return ids if isinstance(ids, list) else [ids]

    @property
    def bill_nos(self) -> list:
        return self.result.get("target_bill_nos") or self.result.get("bill_nos") or []

    def __repr__(self):
        return f"OpNode({self.tool}, success={self.is_success}, next={self.next_action})"


# ─────────────────────────────────────────────
# 约束规则定义
# ─────────────────────────────────────────────

def _check_complete_lifecycle(nodes: list[OpNode], **kwargs) -> tuple[bool, str]:
    """RULE-001: 写操作必须走完完整生命周期

    检查写操作（save/submit/push）是否有对应的后续操作完成生命周期。
    next_action != null 时，AI 不应终止工作。
    """
    for node in nodes:
        if node.tool in ("kingdee_save_bill", "kingdee_push_bill", "kingdee_submit_bills"):
            if node.is_success and node.next_action:
                # 还有后续步骤，检查是否有对应的后续操作
                fid = node.fid or (node.bill_ids[0] if node.bill_ids else None)
                if not fid:
                    return True, ""  # 无法追踪，跳过

                # 查找对应的后续操作
                has_followup = False
                for later in nodes:
                    if later.timestamp <= node.timestamp:
                        continue
                    if later.tool == f"kingdee_{node.next_action.replace('+', '_').split('_')[0]}_bills":
                        if fid in (later.params.get("bill_ids") or later.bill_ids or []):
                            has_followup = True
                            break

                if not has_followup:
                    return False, (
                        f"[RULE-001] 操作链不完整: {node.tool} 返回 next_action={node.next_action}，"
                        f"但未检测到对应的后续操作 kingdee_{node.next_action.replace('+', '_').split('_')[0]}_bills。"
                        f"单据 FID={fid} 可能处于未完成状态。"
                        f"建议: 继续调用 kingdee_{node.next_action.replace('+', '_').split('_')[0]}_bills 完成生命周期。"
                    )
    return True, ""


def _check_push_chain(nodes: list[OpNode], **kwargs) -> tuple[bool, str]:
    """RULE-002: Push 操作后必须紧跟 Submit + Audit

    下推生成的目标单据必须完成提交+审核才算完整流程。
    """
    for node in nodes:
        if node.tool == "kingdee_push_bill":
            if not node.is_success:
                continue
            target_nos = node.bill_nos
            if not target_nos:
                target_nos = node.result.get("source_bill_nos", [])

            # Push 后应该紧跟 submit，然后 audit
            submit_done = False
            audit_done = False
            for later in nodes:
                if later.timestamp <= node.timestamp:
                    continue
                if later.tool == "kingdee_submit_bills":
                    # 检查是否提交了正确的单据
                    submit_ids = later.params.get("bill_ids") or later.bill_ids or []
                    # 由于 push 返回的是 target_bill_nos 而非 fid，这里简化为检查是否有提交操作
                    submit_done = True
                if later.tool == "kingdee_audit_bills":
                    audit_done = True

            if target_nos and not (submit_done and audit_done):
                return False, (
                    f"[RULE-002] Push 操作未完成后续流程: kingdee_push_bill 生成了 {len(target_nos)} 张目标单据，"
                    f"但未检测到完整的 submit+audit 链。"
                    f"目标单据: {target_nos}。"
                    f"建议: 调用 kingdee_submit_bills 提交，再调用 kingdee_audit_bills 审核。"
                )
    return True, ""


def _check_error_recovery(nodes: list[OpNode], **kwargs) -> tuple[bool, str]:
    """RULE-003: 错误之后必须有修正动作

    当操作返回 errors 时，后续必须有对应的修正操作（不等于原操作重试）。
    """
    for i, node in enumerate(nodes):
        # 检查是否有错误
        has_error = (
            node.result.get("error") or
            (node.result.get("errors") and len(node.result.get("errors", [])) > 0) or
            not node.is_success
        )
        if has_error:
            # 查找后续是否有修正动作
            # 修正动作定义：调用了不同的工具，或相同的工具但参数不同
            has_recovery = False
            for later in nodes[i+1:]:
                if later.tool != node.tool:
                    has_recovery = True
                    break
                # 同工具但参数不同也算修正
                if later.params != node.params:
                    has_recovery = True
                    break

            if not has_recovery:
                # 检查是否已经是最后一个操作
                if i == len(nodes) - 1:
                    return False, (
                        f"[RULE-003] 操作失败但无后续修正: {node.tool} 返回了错误或 success=false，"
                        f"但这是最后一个操作，没有修正动作。"
                        f"错误: {node.result.get('errors', node.result)}。"
                        f"建议: 根据错误信息（errors 中的 reason/suggestion）采取修正行动，"
                        f"或调用 kingdee_view_bill 查看单据详情后重新操作。"
                    )
    return True, ""


def _check_idempotent_read_only(nodes: list[OpNode], **kwargs) -> tuple[bool, str]:
    """RULE-004: 读操作之后应验证结果而非盲目重复

    查询操作（readOnlyHint=true）连续调用且返回相同结果时，视为无效重复。
    """
    if len(nodes) < 2:
        return True, ""

    # 找到连续的非幂等操作
    for i in range(len(nodes) - 1):
        curr = nodes[i]
        nxt = nodes[i + 1]

        # 跳过写操作（需要单独检查）
        if curr.tool in ("kingdee_save_bill", "kingdee_submit_bills", "kingdee_audit_bills",
                          "kingdee_unaudit_bills", "kingdee_delete_bills", "kingdee_push_bill"):
            continue

        # 两个相同的查询操作且结果相同
        if curr.tool == nxt.tool and curr.params == nxt.params:
            curr_data = curr.result.get("data", curr.result.get("count", 0))
            nxt_data = nxt.result.get("data", nxt.result.get("count", 0))
            if curr_data == nxt_data and curr_data:
                return False, (
                    f"[RULE-004] 无效重复查询: {curr.tool} 连续调用两次，返回相同结果。"
                    f"count={curr_data}。"
                    f"建议: 如果目的是查询最新状态，应在操作之间插入实际修改动作。"
                )
    return True, ""


# ─────────────────────────────────────────────
# 规则注册表
# ─────────────────────────────────────────────

HARNESS_RULES: list[HarnessRule] = [
    HarnessRule(
        id="RULE-001",
        name="生命周期完整性",
        description="写操作必须走完 Save→Submit→Audit 完整链路，next_action != null 时不得终止",
        severity="error",
        check=_check_complete_lifecycle,
    ),
    HarnessRule(
        id="RULE-002",
        name="Push 操作链完整性",
        description="Push 生成的目标单据必须完成 Submit+Audit",
        severity="error",
        check=_check_push_chain,
    ),
    HarnessRule(
        id="RULE-003",
        name="错误恢复检查",
        description="操作失败后必须有对应的修正动作，不能直接终止",
        severity="error",
        check=_check_error_recovery,
    ),
    HarnessRule(
        id="RULE-004",
        name="无效重复查询",
        description="连续相同查询且结果相同时视为无效重复",
        severity="warning",
        check=_check_idempotent_read_only,
    ),
]


def validate_operation_chain(nodes: list[OpNode]) -> list[dict]:
    """验证操作链是否符合 Harness 约束

    返回违规列表，每项包含 rule_id, name, message, severity
    """
    violations = []
    for rule in HARNESS_RULES:
        violated, message = rule.check(nodes)
        if not violated:
            violations.append({
                "rule_id": rule.id,
                "name": rule.name,
                "message": message,
                "severity": rule.severity,
            })
    return violations