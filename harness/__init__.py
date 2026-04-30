"""
Harness — Kingdee MCP 操作约束与反馈循环层

核心模块：
- rules:     操作链完整性约束规则（RULE-001 ~ RULE-004）
- feedback_loop: Agent-to-Agent 审查与 Loop Hints 生成
- failure_trace: 失败模式 → 文档追溯系统

用法：
    from harness import FeedbackLoop, validate_operation_chain

    # 追踪操作链
    tracker = FeedbackLoop()
    hint = tracker.record("save", params, result)
    violations = tracker.check_violations()
"""

from harness.rules import (
    HARNESS_RULES,
    OpNode,
    HarnessRule,
    validate_operation_chain,
)
from harness.feedback_loop import (
    FeedbackLoop,
    generate_loop_hint,
)

__all__ = [
    "HARNESS_RULES",
    "OpNode",
    "HarnessRule",
    "validate_operation_chain",
    "FeedbackLoop",
    "generate_loop_hint",
]