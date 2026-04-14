#!/usr/bin/env python3
"""
check_harness.py — 操作链约束检查工具

用法：
    python scripts/check_harness.py --trace <trace.json>   # 检查操作链trace文件
    python scripts/check_harness.py --last                 # 检查最近的对话trace（从日志读取）

示例 trace.json 格式：
{
  "operations": [
    {
      "tool": "kingdee_save_bill",
      "params": {"form_id": "PUR_PurchaseOrder", "model": {...}},
      "result": {"op": "save", "success": true, "fid": "100001", "next_action": "submit"},
      "timestamp": 1710000000.0
    }
  ]
}

CI 集成：
    python scripts/check_harness.py --trace trace.json || exit 1
    # 任何 error 级别违规都会导致 exit code != 0
"""

import json
import argparse
import os
import sys
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from harness.rules import OpNode, validate_operation_chain, HARNESS_RULES


def load_trace(source: str) -> list[OpNode]:
    """从文件或字符串加载操作链"""
    if os.path.isfile(source):
        with open(source, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.loads(source)

    nodes = []
    for op in data.get("operations", []):
        nodes.append(OpNode(
            tool=op["tool"],
            params=op.get("params", {}),
            result=op.get("result", {}),
            timestamp=op.get("timestamp", 0),
        ))
    return nodes


def format_violation(v: dict) -> str:
    """格式化违规输出（Windows 兼容，避免 emoji）"""
    prefix = {
        "error": "[ERROR]",
        "warning": "[WARN] ",
        "info": "[INFO] ",
    }.get(v["severity"], "[----]")

    return f"{prefix} [{v['rule_id']}] {v['name']}\n   {v['message']}"


def run_check(source: str, fail_on_warning: bool = False) -> int:
    """执行检查，返回违规数（0=通过，负数=失败）"""
    try:
        nodes = load_trace(source)
    except Exception as e:
        print(f"[ERROR] Cannot load trace: {e}")
        return -1

    if not nodes:
        print("[INFO] No operations recorded, skip check")
        return 0

    violations = validate_operation_chain(nodes)

    if not violations:
        print(f"[OK] Harness check passed for {len(nodes)} operations")
        return 0

    # 分组输出
    errors = [v for v in violations if v["severity"] == "error"]
    warnings = [v for v in violations if v["severity"] == "warning"]

    if errors:
        print(f"\n[ERROR] Found {len(errors)} error-level violations:\n")
        for v in errors:
            print(format_violation(v))
            print()

    if warnings:
        print(f"\n[WARN] Found {len(warnings)} warning-level issues:\n")
        for v in warnings:
            print(format_violation(v))
            print()

    if errors or (fail_on_warning and warnings):
        print(f"\n[INFO] Rule reference:")
        for rule in HARNESS_RULES:
            print(f"   [{rule.id}] {rule.name}: {rule.description}")
        return len(errors)

    return 0


def main():
    parser = argparse.ArgumentParser(description="Harness 操作链约束检查")
    parser.add_argument("--trace", type=str, help="trace.json 文件路径")
    parser.add_argument("--last", action="store_true", help="读取最近的对话日志")
    parser.add_argument("--fail-on-warning", action="store_true", help="警告也导致 exit code != 0")
    parser.add_argument("--rules", action="store_true", help="列出所有规则")
    args = parser.parse_args()

    if args.rules:
        print("Harness rules list:\n")
        for rule in HARNESS_RULES:
            icon = {"error": "[ERROR]", "warning": "[WARN]", "info": "[INFO]"}.get(rule.severity, "[----]")
            print(f"{icon} [{rule.id}] {rule.name}")
            print(f"   level: {rule.severity}")
            print(f"   desc: {rule.description}\n")
        return 0

    source = args.trace
    if args.last:
        # TODO: 从日志目录读取最近的 trace
        print("TODO: --last 模式从日志目录读取")
        return 0

    if not source:
        parser.print_help()
        return 0

    exit_code = run_check(source, args.fail_on_warning)
    sys.exit(min(exit_code, 1) if exit_code > 0 else 0)


if __name__ == "__main__":
    sys.exit(main())