"""
失败追溯系统 — 从实际错误中学习

核心原理：
- 每次真实错误都记录到 failure_log.jsonl
- 定期扫描失败日志，提取新模式追加到 KNOWN_ERROR_PATTERNS
- 每个失败条目带来源追踪（哪次对话/哪个场景）

格式（failure_log.jsonl）：
{
    "timestamp": "2026-04-14T10:00:00Z",
    "op": "push",
    "error_type": "convert",
    "message": "关联数量已达上限",
    "context": {
        "form_id": "PUR_PurchaseOrder",
        "target_form_id": "STK_InStock",
        "source_bill_nos": ["CGDD000025"]
    },
    "resolved": false,
    "resolution": null
}

用法：
    python scripts/extract_failures.py --scan     # 扫描失败日志，提取新模式
    python scripts/extract_failures.py --report   # 生成失败模式报告
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, asdict


# 失败日志文件
FAILURE_LOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "examples", "failure_log.jsonl"
)


@dataclass
class FailureEntry:
    """失败条目"""
    timestamp: str
    op: str
    error_type: str      # "http" | "business" | "convert" | "validation" | "unknown"
    message: str
    context: dict        # 操作上下文（form_id, params 等）
    resolved: bool = False
    resolution: Optional[str] = None
    pattern_id: Optional[str] = None  # 关联到 KNOWN_ERROR_PATTERNS 的索引


class FailureLogger:
    """失败日志记录器"""

    def __init__(self, log_path: str = FAILURE_LOG_PATH):
        self.log_path = log_path

    def log(self, op: str, result: dict, error_info: dict = None) -> None:
        """记录一次失败（由 server.py 在错误时调用）

        Args:
            op: 操作类型
            result: 操作返回的完整结果（包含 errors）
            error_info: 可选的额外错误信息
        """
        errors = result.get("errors", []) or []
        if not errors and not result.get("error"):
            return  # 没有错误，不记录

        for err in (errors if errors else [{"type": "unknown", "message": str(result)}]):
            entry = FailureEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                op=op,
                error_type=err.get("type", "unknown"),
                message=err.get("message", err.get("raw", "")),
                context={
                    "op": op,
                    "form_id": result.get("form_id", ""),
                    "fid": result.get("fid", result.get("bill_id", "")),
                    "matched_reason": err.get("matched", {}).get("reason", ""),
                },
                resolved=False,
            )
            self._append(entry)

    def _append(self, entry: FailureEntry) -> None:
        """追加到日志文件"""
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")


class FailureAnalyzer:
    """失败模式分析器"""

    def __init__(self, log_path: str = FAILURE_LOG_PATH):
        self.log_path = log_path

    def load_entries(self) -> list[FailureEntry]:
        """加载所有失败条目"""
        if not os.path.exists(self.log_path):
            return []

        entries = []
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    d = json.loads(line)
                    entries.append(FailureEntry(**d))
        return entries

    def extract_new_patterns(self) -> list[tuple[str, str, str]]:
        """从失败日志中提取新模式（追加到 KNOWN_ERROR_PATTERNS）

        扫描所有未标记 resolved 的失败条目，
        提取与 KNOWN_ERROR_PATTERNS 不重复的新模式。
        """
        # 读取当前的 pattern
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        try:
            from server import KNOWN_ERROR_PATTERNS
            existing_patterns = [p[0].lower() for p in KNOWN_ERROR_PATTERNS]
        except ImportError:
            existing_patterns = []

        new_patterns = []
        for entry in self.load_entries():
            if entry.resolved:
                continue
            if entry.error_type == "unknown":
                continue

            msg_lower = entry.message.lower()
            # 检查是否已存在
            if any(p in msg_lower for p in existing_patterns):
                continue

            # 生成新 pattern
            reason = entry.context.get("matched_reason", "") or f"未知原因（{entry.error_type}）"
            suggestion = self._generate_suggestion(entry)
            new_patterns.append((entry.message[:50], reason, suggestion))

        return new_patterns

    def _generate_suggestion(self, entry: FailureEntry) -> str:
        """根据错误类型生成建议"""
        type_suggestions = {
            "http": "检查服务器配置和网络连接",
            "business": "检查业务规则限制（如关联数量、单据状态）",
            "convert": "尝试显式指定 rule_id，或检查源单据状态",
            "validation": "检查参数格式和数据类型是否正确",
            "timeout": "检查服务器连通性或增加超时时间",
        }
        return type_suggestions.get(entry.error_type, "查看单据详情后重试")

    def generate_report(self) -> dict:
        """生成失败模式报告（用于分析）"""
        entries = self.load_entries()
        if not entries:
            return {"summary": "暂无失败记录", "entries": []}

        # 按 error_type 分组
        by_type: dict[str, list] = {}
        for entry in entries:
            by_type.setdefault(entry.error_type, []).append(entry)

        # 统计
        total = len(entries)
        resolved = sum(1 for e in entries if e.resolved)
        unresolved = total - resolved

        # 提取未解决的高频错误
        unresolved_messages: dict[str, int] = {}
        for entry in entries:
            if not entry.resolved:
                key = entry.message[:80]
                unresolved_messages[key] = unresolved_messages.get(key, 0) + 1

        top_unresolved = sorted(
            unresolved_messages.items(), key=lambda x: x[1], reverse=True
        )[:5]

        return {
            "summary": {
                "total_failures": total,
                "resolved": resolved,
                "unresolved": unresolved,
            },
            "by_type": {
                t: len(es) for t, es in by_type.items()
            },
            "top_unresolved_errors": [
                {"message": msg, "count": cnt} for msg, cnt in top_unresolved
            ],
            "new_patterns": self.extract_new_patterns(),
        }


def run_scan() -> None:
    """CLI：扫描失败日志，提取新模式"""
    analyzer = FailureAnalyzer()
    report = analyzer.generate_report()

    print("=== 失败模式报告 ===\n")
    print(f"总失败数: {report['summary']['total_failures']}")
    print(f"已解决:   {report['summary']['resolved']}")
    print(f"未解决:   {report['summary']['unresolved']}\n")

    print("按类型分布:")
    for t, cnt in report["by_type"].items():
        print(f"  {t}: {cnt}")

    print("\n未解决的高频错误:")
    for item in report["top_unresolved_errors"]:
        print(f"  [{item['count']}次] {item['message']}")

    new_patterns = report.get("new_patterns", [])
    if new_patterns:
        print(f"\n建议追加的新模式 ({len(new_patterns)} 条):")
        for pattern, reason, suggestion in new_patterns:
            print(f"  - {pattern}")
            print(f"    原因: {reason}")
            print(f"    建议: {suggestion}")
    else:
        print("\n未发现需要追加的新模式")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="失败追溯系统")
    parser.add_argument("--scan", action="store_true", help="扫描失败日志")
    parser.add_argument("--report", action="store_true", help="生成报告")
    args = parser.parse_args()

    if args.scan or args.report:
        run_scan()
    else:
        parser.print_help()