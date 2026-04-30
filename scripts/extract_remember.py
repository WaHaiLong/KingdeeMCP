#!/usr/bin/env python3
"""
extract_remember.py — 扫描代码中的 💡 REMEMBER 注释，提取记忆条目

用法：
    python scripts/extract_remember.py              # 打印所有条目
    python scripts/extract_remember.py --update    # 追加到记忆文件
    python scripts/extract_remember.py --file src/  # 指定扫描目录
"""

import os
import re
import sys
import argparse
from datetime import datetime

# 修复 Windows 终端中文/emoji 输出
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

MEMORY_FILE = os.path.join(
    os.path.dirname(__file__), "..", "C:\\Users\\ZnL\\.claude\\projects\\D--projects\\memory\\MEMORY.md"
)
REMEMBER_PATTERN = re.compile(r"#\s*💡\s*REMEMBER:\s*(.+)")
DEFAULT_SCAN_DIR = os.path.join(os.path.dirname(__file__), "..", "src")


def scan_directory(root_dir: str) -> list[dict]:
    """扫描目录下所有代码文件，提取 💡 REMEMBER 注释"""
    entries = []
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if not filename.endswith((".py", ".js", ".ts", ".go", ".java", ".rs")):
                continue
            filepath = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(filepath, os.path.dirname(root_dir))
            with open(filepath, encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    match = REMEMBER_PATTERN.search(line)
                    if match:
                        raw = match.group(1).strip()
                        # 尝试用 — 或 - 分隔描述和详情
                        sep = re.search(r"\s*[—\-]\s*", raw)
                        if sep:
                            desc = raw[:sep.start()].strip()
                            detail = raw[sep.end():].strip()
                        else:
                            desc = raw
                            detail = ""
                        entries.append({
                            "description": desc,
                            "detail": detail,
                            "file": rel_path,
                            "line": lineno,
                        })
    return entries


def format_entries(entries: list[dict]) -> str:
    """格式化记忆条目为 Markdown"""
    lines = [f"\n## 自动提取记忆 ({datetime.now().strftime('%Y-%m-%d')})\n"]
    if not entries:
        lines.append("*（本次扫描无 💡 REMEMBER 条目）*\n")
        return "\n".join(lines)

    current_file = None
    for e in entries:
        if e["file"] != current_file:
            current_file = e["file"]
            lines.append(f"\n### {current_file}\n")
        detail = f" — {e['detail']}" if e["detail"] else ""
        lines.append(f"- **{e['description']}**{detail} _(L{e['line']})_\n")
    return "\n".join(lines)


def update_memory_file(entries: list[dict], memory_path: str) -> None:
    """追加提取的记忆条目到记忆文件"""
    section = format_entries(entries)

    with open(memory_path, encoding="utf-8") as f:
        content = f.read()

    # 检查是否已有同名章节
    marker = f"## 自动提取记忆 ({datetime.now().strftime('%Y-%m-%d')})"
    if marker in content:
        print(f"[skip] 今日记忆已存在: {marker}")
        return

    with open(memory_path, "a", encoding="utf-8") as f:
        f.write(section)
    print(f"[ok] 追加 {len(entries)} 条记忆到 {memory_path}")


def main():
    parser = argparse.ArgumentParser(description="提取 💡 REMEMBER 注释为记忆条目")
    parser.add_argument("--dir", default=DEFAULT_SCAN_DIR, help="扫描目录")
    parser.add_argument("--update", action="store_true", help="追加到记忆文件")
    parser.add_argument("--memory", default=MEMORY_FILE, help="记忆文件路径")
    args = parser.parse_args()

    scan_dir = os.path.normpath(args.dir)
    print(f"扫描目录: {scan_dir}")

    entries = scan_directory(scan_dir)
    print(f"找到 {len(entries)} 条 [REMEMBER] 记录\n")

    output = format_entries(entries)
    print(output)

    if args.update:
        update_memory_file(entries, args.memory)


if __name__ == "__main__":
    main()
