"""评估入口：一条命令跑完所有用例，输出指标并和上次基线对比。

用法:
    python -m evals.run_eval                     # 跑全部用例
    python -m evals.run_eval --dry-run           # 离线自检管线（mock agent + mock 账套状态）
    python -m evals.run_eval --tags 高频          # 只跑带某标签的用例
    python -m evals.run_eval --category 采购订单
    python -m evals.run_eval --format markdown -o report.md
    python -m evals.run_eval --no-baseline       # 不写入基线（试跑）

退出码:
    0 = 成功率达到 thresholds.min_pass_rate
    1 = 成功率未达标 / 出现回归（便于接 CI 门禁）
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from . import config as cfg
from . import metrics as metrics_mod
from . import report as report_mod
from .agent import build_agent
from .graders import ResultGrader, RuleGrader, TrajectoryGrader
from .runner import load_cases, run_all
from .sandbox.reset import Sandbox


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="KingdeeMCP 评估层")
    p.add_argument("--config", default=None, help="config.yaml 路径")
    p.add_argument("--cases-dir", default=None, help="用例目录")
    p.add_argument("--tags", nargs="*", default=None, help="只跑带这些标签的用例")
    p.add_argument("--category", nargs="*", default=None, help="只跑这些类别的用例")
    p.add_argument("--dry-run", action="store_true",
                   help="离线自检：mock agent + mock 账套状态，不连金蝶、不写数据")
    p.add_argument("--format", default=None, choices=["text", "markdown", "json"])
    p.add_argument("-o", "--output", default=None, help="把报告写到文件")
    p.add_argument("--no-baseline", action="store_true", help="不写入基线（试跑）")
    return p.parse_args(argv)


def _has_write_cases(cases) -> bool:
    for c in cases:
        if (c.get("expected_result") or {}).get("assertions"):
            # 含写操作工具的用例需要安全闸
            wt = {"kingdee_save_bill", "kingdee_submit_bills", "kingdee_audit_bills",
                  "kingdee_upload_attachment",
                  "kingdee_unaudit_bills", "kingdee_delete_bills", "kingdee_push_bill",
                  "kingdee_create_and_audit", "kingdee_push_and_audit", "kingdee_save_asset"}
            if wt & set(c.get("expected_tools", [])):
                return True
        if (c.get("setup") or {}).get("fixtures"):
            return True
    return False


async def _main_async(args) -> int:
    config = cfg.load_config(args.config)
    fmt = args.format or config.get("output", {}).get("report_format", "text")

    cases = load_cases(args.cases_dir, tags=args.tags, categories=args.category)
    if not cases:
        print("没有匹配的用例。", file=sys.stderr)
        return 1

    # 安全闸：非 dry-run 且存在写操作/夹具用例时，必须确认是测试账套
    if not args.dry_run and _has_write_cases(cases):
        cfg.assert_safe_for_writes(config)

    agent = build_agent(config)
    sandbox = Sandbox(config, dry_run=args.dry_run)
    graders = [ResultGrader(config), TrajectoryGrader(config), RuleGrader(config)]

    results = await run_all(cases, agent, sandbox, graders, dry_run=args.dry_run)
    metrics = metrics_mod.aggregate(results)

    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "agent_type": config.get("agent", {}).get("type"),
        "metrics": metrics,
        "results": results,
    }

    baselines_dir = config.get("output", {}).get("baselines_dir", "evals/baselines")
    previous = report_mod.load_previous_baseline(baselines_dir)
    diff = report_mod.compare_to_previous(payload, previous)

    rendered = report_mod.render(payload, diff, fmt=fmt)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
        print(f"报告已写入 {args.output}")
    else:
        print(rendered)

    # dry-run 是管线自检（mock 数据），不写入真实基线，避免污染回归对比
    if not args.no_baseline and not args.dry_run:
        saved = report_mod.save_baseline(payload, baselines_dir)
        print(f"基线已保存: {saved}")
    elif args.dry_run:
        print("（dry-run：自检模式，未写入基线）")

    # 退出码：成功率门禁 + 回归报警
    min_rate = config.get("thresholds", {}).get("min_pass_rate", 0.0)
    if metrics["pass_rate"] < min_rate:
        print(f"成功率 {metrics['pass_rate']:.1%} < 门槛 {min_rate:.1%}", file=sys.stderr)
        return 1
    if diff.get("regressions"):
        print(f"检测到回归: {diff['regressions']}", file=sys.stderr)
        return 1
    return 0


def main(argv=None) -> int:
    # Windows 控制台默认 GBK，会把报告里的中文/制表符显示成乱码；统一切到 UTF-8。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args = _parse_args(argv)
    try:
        return asyncio.run(_main_async(args))
    except cfg.UnsafeEnvironmentError as e:
        print(f"\n[安全闸] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
