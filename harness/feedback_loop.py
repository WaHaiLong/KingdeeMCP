"""
Harness 反馈循环 — Agent-to-Agent 审查与 Loop Hints

核心原理：
- 每步操作后生成 loop_hint，引导 AI 继续或修正
- 不只是 "next_action"，而是 "if X then Y else Z" 的条件分支
- 错误 → 修正 → 验证 → 再修正的闭环

Loop Hint 格式：
{
    "phase": "awaiting_submit" | "awaiting_audit" | "verify" | "complete" | "recover",
    "status": "ok" | "warning" | "error",
    "message": str,          # 人类可读状态描述
    "actions": {             # 分支动作
        "if_ok": [...],      # 成功时建议
        "if_error": [...],   # 错误时建议
        "if_repeat": [...],  # 重复操作时建议
    },
    "verify": {...},         # 验证步骤（如有）
    "metadata": {           # 上下文（用于追溯）
        "op": str,
        "fid": str,
        "prev_errors": [...],
    }
}
"""

from typing import Any, Optional


def generate_loop_hint(op: str, result: dict, prev_hint: dict = None) -> dict:
    """生成操作后的 Loop Hint（反馈循环核心函数）

    这是 Agent-to-Agent 审查的关键：
    - 接收前一步的 hint 和当前结果
    - 判断状态（ok/warning/error）
    - 生成下一步建议（分 branch）
    - 如果状态不对，循环回模型修正

    Args:
        op: 操作类型（save/submit/audit/unaudit/delete/push）
        result: 操作返回的完整结构化结果
        prev_hint: 上一步的 loop_hint（用于关联追踪）

    Returns:
        dict: Loop Hint，包含 phase / status / actions / verify
    """
    success = result.get("success", False)
    errors = result.get("errors", [])
    next_action = result.get("next_action")
    fid = result.get("fid") or result.get("bill_id")
    bill_nos = result.get("target_bill_nos") or result.get("bill_nos", [])

    # ── Phase 1: 操作成功 ──────────────────────────
    if success:
        if next_action:
            # 还有后续步骤
            phase_map = {
                "submit":  ("awaiting_audit",  "单据已提交，等待审核"),
                "audit":   ("complete",        "单据已审核生效"),
                "submit+audit": ("awaiting_audit", "目标单已生成，等待提交+审核"),
            }
            phase, msg = phase_map.get(next_action, (next_action, f"等待 {next_action}"))

            actions = {"if_ok": [], "if_error": [], "if_repeat": []}
            if next_action == "submit":
                actions["if_ok"] = [
                    {
                        "tool": "kingdee_submit_bills",
                        "desc": "提交单据至审核队列",
                        "params_hint": f"bill_ids=[{fid}]",
                    }
                ]
            elif next_action == "submit+audit":
                actions["if_ok"] = [
                    {
                        "tool": "kingdee_submit_bills",
                        "desc": "提交目标单据",
                        "params_hint": f"bill_ids 对应 {bill_nos}",
                    },
                    {
                        "tool": "kingdee_audit_bills",
                        "desc": "审核目标单据",
                        "params_hint": f"bill_ids 对应 {bill_nos}",
                    },
                ]
            elif next_action == "audit":
                actions["if_ok"] = [
                    {
                        "tool": "kingdee_audit_bills",
                        "desc": "审核单据使其生效",
                        "params_hint": f"bill_ids=[{fid}]",
                    }
                ]

            return {
                "phase": phase,
                "status": "ok",
                "message": msg,
                "actions": actions,
                "verify": _build_verify_step(op, result),
                "metadata": {"op": op, "fid": fid, "bill_nos": bill_nos},
            }
        else:
            # next_action == null，表示流程完成
            return {
                "phase": "complete",
                "status": "ok",
                "message": "操作完成",
                "actions": {
                    "if_ok": [
                        {
                            "tool": "kingdee_query_bills",
                            "desc": "验证操作结果",
                            "params_hint": f"filter_string=FID={fid}",
                        }
                    ],
                    "if_error": [],
                    "if_repeat": [],
                },
                "verify": _build_verify_step(op, result),
                "metadata": {"op": op, "fid": fid},
            }

    # ── Phase 2: 操作失败 ──────────────────────────
    # 构建错误分支建议
    error_actions = []
    for err in errors:
        matched = err.get("matched", {})
        if matched:
            error_actions.append({
                "reason": matched.get("reason", ""),
                "suggestion": matched.get("suggestion", ""),
            })
        else:
            # 未知错误，通用建议
            error_actions.append({
                "reason": err.get("message", "未知错误"),
                "suggestion": "调用 kingdee_view_bill 查看详情，或 kingdee_get_fields 确认可用字段",
            })

    # 根据错误类型建议修正路径
    recovery_options = _build_recovery_options(op, result, errors)

    return {
        "phase": "recover",
        "status": "error",
        "message": f"操作失败，发现 {len(errors)} 个错误",
        "actions": {
            "if_ok": [],
            "if_error": recovery_options,
            "if_repeat": [
                {
                    "tool": "kingdee_view_bill",
                    "desc": "查看单据详情确认当前状态",
                    "params_hint": f"form_id, bill_id={fid}",
                },
                {
                    "tool": "kingdee_query_bills",
                    "desc": "重新查询确认状态",
                    "params_hint": f"filter_string=FID={fid}",
                },
            ],
        },
        "errors": errors,
        "metadata": {"op": op, "fid": fid, "error_count": len(errors)},
    }


def _build_verify_step(op: str, result: dict) -> Optional[dict]:
    """为操作构建验证步骤

    验证是反馈循环的关键：操作完成后验证是否真的生效，
    而不是只看 API 返回 success。
    """
    fid = result.get("fid") or result.get("bill_id")
    form_id = result.get("form_id") or _infer_form_id(op, result)

    if not fid:
        return None

    verify = {
        "tool": "kingdee_query_bills",
        "desc": "验证操作是否生效（查询单据当前状态）",
        "expected_status": _get_expected_status(op),
        "params": {
            "form_id": form_id,
            "filter_string": f"FID={fid}",
            "field_keys": "FID,FBillNo,FDocumentStatus",
        },
        "check": f"FDocumentStatus 应为 {_get_expected_status(op)}",
    }
    return verify


def _build_recovery_options(op: str, result: dict, errors: list) -> list:
    """根据错误类型构建修正路径"""
    options = []

    for err in errors:
        msg = err.get("message", "").lower()
        err_type = err.get("type", "unknown")
        matched = err.get("matched", {})

        # HTTP 错误修复
        if err_type == "http":
            code = err.get("code", "")
            if code == 401:
                options.append({
                    "tool": "重新检查环境变量配置",
                    "desc": "认证失败，检查 KINGDEE_APP_ID / KINGDEE_APP_SEC 是否正确",
                    "params_hint": "",
                })
            elif code in (502, 404):
                options.append({
                    "tool": "检查配置",
                    "desc": matched.get("suggestion", "检查 KINGDEE_SERVER_URL 和 HTTP 版本配置"),
                    "params_hint": "",
                })

        # 业务错误修复
        if matched:
            reason = matched.get("reason", "")
            if "关联数量" in reason or "下推" in reason:
                options.append({
                    "tool": "kingdee_query_purchase_order_progress",
                    "desc": "查询采购订单执行进度，确认实际收料/入库数量",
                    "params_hint": "filter_string=FBillNo='...'",
                })
            if "字段不存在" in reason:
                options.append({
                    "tool": "kingdee_get_fields",
                    "desc": "确认该表单在当前账套的实际可用字段",
                    "params_hint": f"form_id={err.get('field', '')} 或对应表单",
                })
            if "单据状态" in reason:
                options.append({
                    "tool": "kingdee_view_bill",
                    "desc": "查看单据当前状态",
                    "params_hint": f"bill_id={fid}",
                })
            if "权限" in reason:
                options.append({
                    "tool": "手动处理",
                    "desc": "联系金蝶管理员开通集成用户的操作权限",
                    "params_hint": "",
                })

        # ConvertResponseStatus 错误（Push 操作）
        if err_type == "convert":
            options.append({
                "tool": "检查转换规则",
                "desc": f"第 {err.get('row', '?')} 行转换失败: {err.get('message', '')}。尝试显式指定 rule_id",
                "params_hint": "rule_id='PUR_PurchaseOrder-STK_InStock'",
            })

        # 通用修复（如果没有匹配到具体建议）
        fid = result.get("fid") or result.get("bill_id")
        if not any(o.get("desc") for o in options):
            options.append({
                "tool": "kingdee_view_bill",
                "desc": "查看单据完整数据，了解失败原因",
                "params_hint": f"form_id, bill_id={fid or '未知'}",
            })

    return options


def _infer_form_id(op: str, result: dict) -> str:
    """从操作结果推断 form_id"""
    return result.get("form_id", "未知")


def _get_expected_status(op: str) -> str:
    """每个操作完成后，单据应该处于的状态"""
    status_map = {
        "save":    "Z（暂存/草稿）",
        "submit":  "A 或 B（创建/审核中）",
        "audit":   "C（已审核）",
        "unaudit": "B 或 D（审核中/重新审核）",
        "delete":  "已删除（查询应无结果）",
        "push":    "Z（暂存/草稿，目标单据）",
    }
    return status_map.get(op, "未知")


class FeedbackLoop:
    """反馈循环追踪器

    用于追踪整个操作序列的 Feedback Loop 状态。
    每次操作后调用 .record() 记录，调用 .check() 检查是否有违规。
    """

    def __init__(self):
        self.nodes: list[dict] = []  # 每个操作的 {op, result, loop_hint}
        self.violations: list[dict] = []  # 发现的违规

    def record(self, op: str, params: dict, result: dict) -> dict:
        """记录一次操作并生成 loop_hint"""
        prev = self.nodes[-1]["loop_hint"] if self.nodes else None
        hint = generate_loop_hint(op, result, prev)

        self.nodes.append({
            "op": op,
            "params": params,
            "result": result,
            "loop_hint": hint,
        })
        return hint

    def check_violations(self) -> list[dict]:
        """检查当前链路的违规情况（RULE-001/002/003 自动检查）"""
        # 导入延迟避免循环依赖
        from harness.rules import validate_operation_chain, OpNode

        nodes = []
        for i, node_data in enumerate(self.nodes):
            result = node_data["result"]
            nodes.append(OpNode(
                tool=f"kingdee_{node_data['op']}" if not node_data['op'].startswith("kingdee_") else node_data['op'],
                params=node_data["params"],
                result=result,
                timestamp=float(i),
            ))

        self.violations = validate_operation_chain(nodes)
        return self.violations

    def summary(self) -> dict:
        """生成反馈循环摘要"""
        phases = [n["loop_hint"].get("phase", "?") for n in self.nodes]
        errors = [n for n in self.nodes if n["loop_hint"].get("status") == "error"]

        return {
            "total_operations": len(self.nodes),
            "phase_sequence": " → ".join(phases),
            "error_count": len(errors),
            "violations": self.violations,
            "complete": phases[-1] == "complete" if phases else False,
        }

    def get_latest_hint(self) -> Optional[dict]:
        """获取最新的 loop_hint（用于引导 AI 下一步）"""
        if not self.nodes:
            return None
        return self.nodes[-1]["loop_hint"]