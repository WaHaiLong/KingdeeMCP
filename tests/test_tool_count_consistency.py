"""
对外声明的「工具数 / 业务域数 / 版本号」与代码实际值的一致性回归测试

背景：
    server.json 是发布到官方 MCP Registry 的清单，它的 description 会被
    lobehub / himcp / PulseMCP 等聚合站直接抓走展示。发版前它写的是
    "87 tools, 13 domains"，而代码里实际注册了 99 个 @mcp.tool；
    README 顶部写 99，下面的业务域表格加起来却是 87 —— 三处对不上，
    等于对外少报 12 个工具。这类错误不会让程序崩，所以跑再多功能测试也发现不了，
    只能靠一致性校验拦住。

    同类风险还有版本号：tag 打 v0.2.2，但 pyproject / __init__ / server.json
    里任意一处还停在旧版本，发布流水线要么发错版本、要么被 PyPI 以
    「版本已存在」拒绝，而这时候 tag 已经推上去了，回滚很难看。

因此本测试锁死三件事：
    1. 代码实际 @mcp.tool 数量 == README 顶部声明 == README 表格合计 == server.json description
    2. 业务域数量：README 表格行数 == README 顶部声明 == server.json description
    3. 版本号：pyproject.toml == __init__.py == server.json(顶层 + packages[0])
    4. server.json description ≤ 100 字符（官方 Registry 的硬限制，超了直接被拒收）
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVER_PY = ROOT / "src" / "kingdee_mcp" / "server.py"
INIT_PY = ROOT / "src" / "kingdee_mcp" / "__init__.py"
README = ROOT / "README.md"
SERVER_JSON = ROOT / "server.json"
PYPROJECT = ROOT / "pyproject.toml"
SKILL_DIR = ROOT / "skill"

# 官方 MCP Registry 对 description 的长度上限（实测：超过即校验失败）
REGISTRY_DESCRIPTION_MAX = 100


def _actual_tool_names() -> list[str]:
    """从源码里数 @mcp.tool 装饰的函数名。

    刻意用文本解析而不是读 FastMCP 内部结构：内部属性名会随版本变，
    而「装饰器 + def」这个形状不会变。
    """
    lines = SERVER_PY.read_text(encoding="utf-8").split("\n")
    names: list[str] = []
    for i, line in enumerate(lines):
        if "@mcp.tool" not in line:
            continue
        for follow in lines[i + 1: i + 8]:
            m = re.match(r"\s*(?:async\s+)?def\s+([A-Za-z_0-9]+)", follow)
            if m:
                names.append(m.group(1))
                break
    return names


def _readme_domain_rows() -> list[tuple[str, int]]:
    """抓「业务域 | 数量 | 代表性工具」那张表的每一行，返回 (域名, 数量)。"""
    rows: list[tuple[str, int]] = []
    for line in README.read_text(encoding="utf-8").split("\n"):
        m = re.match(r"^\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|", line)
        if m:
            rows.append((m.group(1), int(m.group(2))))
    return rows


def _readme_declared_total() -> int:
    """README 里 `共 **99 个工具**` / `- **99 个工具**` 这类声明。"""
    hits = re.findall(r"\*\*(\d+)\s*个工具\*\*", README.read_text(encoding="utf-8"))
    assert hits, "README 里找不到 `**N 个工具**` 声明，取数逻辑可能已失效"
    return int(hits[0])


def _server_json() -> dict:
    return json.loads(SERVER_JSON.read_text(encoding="utf-8"))


def test_no_duplicate_tool_names():
    """同名工具注册两次时，后注册的会顶掉前一个，属于静默失效。"""
    names = _actual_tool_names()
    dups = sorted({n for n in names if names.count(n) > 1})
    assert not dups, f"存在重复注册的工具名：{dups}"


def test_readme_total_matches_code():
    actual = len(_actual_tool_names())
    assert actual > 50, f"只解析到 {actual} 个工具，取数逻辑可能已失效"
    assert _readme_declared_total() == actual, (
        f"README 声明 {_readme_declared_total()} 个工具，代码实际 {actual} 个"
    )


def test_readme_domain_table_sums_to_total():
    actual = len(_actual_tool_names())
    rows = _readme_domain_rows()
    assert len(rows) >= 10, f"业务域表格只解析到 {len(rows)} 行，取数逻辑可能已失效"
    total = sum(count for _, count in rows)
    assert total == actual, (
        f"业务域表格合计 {total}，代码实际 {actual} —— "
        f"逐行：{[f'{n}={c}' for n, c in rows]}"
    )


def test_readme_declares_correct_domain_count():
    """顶部『… 等 N 大业务域』要跟表格行数一致。"""
    text = README.read_text(encoding="utf-8")
    m = re.search(r"等\s*(\d+)\s*大业务域", text)
    assert m, "README 里找不到 `等 N 大业务域` 声明"
    assert int(m.group(1)) == len(_readme_domain_rows()), (
        f"README 声明 {m.group(1)} 个业务域，表格实际 {len(_readme_domain_rows())} 行"
    )


def test_server_json_description_matches_code():
    """server.json 会被官方 Registry 和各聚合站原样抓走，数字错了传播面最广。"""
    desc = _server_json()["description"]
    actual = len(_actual_tool_names())
    domains = len(_readme_domain_rows())

    m_tools = re.search(r"(\d+)\s*tools", desc)
    assert m_tools, f"server.json description 里找不到 `N tools`：{desc!r}"
    assert int(m_tools.group(1)) == actual, (
        f"server.json 写 {m_tools.group(1)} tools，代码实际 {actual} 个"
    )

    m_domains = re.search(r"(\d+)\s*domains", desc)
    assert m_domains, f"server.json description 里找不到 `N domains`：{desc!r}"
    assert int(m_domains.group(1)) == domains, (
        f"server.json 写 {m_domains.group(1)} domains，README 表格实际 {domains} 个"
    )


def test_server_json_description_within_registry_limit():
    desc = _server_json()["description"]
    assert len(desc) <= REGISTRY_DESCRIPTION_MAX, (
        f"description 长 {len(desc)} 字符，超过官方 Registry 上限 "
        f"{REGISTRY_DESCRIPTION_MAX}，提交会被拒收"
    )


def test_server_json_keeps_unofficial_disclaimer():
    """项目是第三方开源、非金蝶官方出品；对外清单必须写明，避免品牌争议。"""
    desc = _server_json()["description"]
    assert "Unofficial" in desc or "Third-party" in desc, (
        f"server.json description 缺少第三方/非官方声明：{desc!r}"
    )


def test_version_consistent_across_release_files():
    """任意一处版本号漏改，都会让打完 tag 的发布流水线发错版本或被 PyPI 拒绝。"""
    py_ver = re.search(
        r'^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.M
    )
    assert py_ver, "pyproject.toml 里找不到 version"
    init_ver = re.search(
        r'^__version__\s*=\s*"([^"]+)"', INIT_PY.read_text(encoding="utf-8"), re.M
    )
    assert init_ver, "__init__.py 里找不到 __version__"

    sj = _server_json()
    versions = {
        "pyproject.toml": py_ver.group(1),
        "__init__.py": init_ver.group(1),
        "server.json": sj["version"],
        "server.json/packages[0]": sj["packages"][0]["version"],
    }
    assert len(set(versions.values())) == 1, f"版本号不一致：{versions}"


def test_server_json_pypi_identifier_matches_pyproject():
    """Registry 里登记的包名必须就是 PyPI 上真实存在的包名。"""
    name = re.search(
        r'^name\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.M
    )
    assert name, "pyproject.toml 里找不到 name"
    assert _server_json()["packages"][0]["identifier"] == name.group(1), (
        "server.json 的 PyPI identifier 与 pyproject.toml 的包名不一致"
    )


# --------------------------------------------------------------------------
# skill/**/SKILL.md —— 提交到技能商店（SkillHub）的对外清单
#
# 上一版这几条测试只盯 README + server.json，结果 skill/kingdee-query/SKILL.md
# 里还写着「共 86 个」，CI 全绿地漏了过去。技能商店要实名 + 3~7 个工作日审核，
# 数字错了改一次的代价远高于仓库文件，所以一并锁死。
# --------------------------------------------------------------------------


def _skill_files() -> list[Path]:
    return sorted(SKILL_DIR.rglob("SKILL.md")) if SKILL_DIR.is_dir() else []


def _md_table_domain_rows(text: str) -> list[tuple[str, int]]:
    """抓「业务域 | 数量 | …」形状的表格行，返回 (域名, 数量)。"""
    rows: list[tuple[str, int]] = []
    for line in text.split("\n"):
        m = re.match(r"^\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|", line)
        if m:
            rows.append((m.group(1), int(m.group(2))))
    return rows


@pytest.mark.parametrize("skill_md", _skill_files(), ids=lambda p: p.parent.name)
def test_skill_md_tool_count_matches_code(skill_md: Path):
    """SKILL.md 里出现的每一处「N 个工具」都必须等于代码实际值。"""
    actual = len(_actual_tool_names())
    text = skill_md.read_text(encoding="utf-8")
    claims = [int(n) for n in re.findall(r"(\d+)\s*个工具", text)]
    assert claims, f"{skill_md.relative_to(ROOT)} 里找不到「N 个工具」声明，取数逻辑可能已失效"
    wrong = sorted({c for c in claims if c != actual})
    assert not wrong, (
        f"{skill_md.relative_to(ROOT)} 声明 {wrong} 个工具，代码实际 {actual} 个 —— "
        "这份文件会提交到技能商店，数字必须跟仓库对齐"
    )


@pytest.mark.parametrize("skill_md", _skill_files(), ids=lambda p: p.parent.name)
def test_skill_md_domain_table_agrees_with_readme(skill_md: Path):
    """SKILL.md 的业务域表格要跟 README 同源：行数一致、合计等于工具总数。"""
    text = skill_md.read_text(encoding="utf-8")
    rows = _md_table_domain_rows(text)
    if not rows:
        pytest.skip(f"{skill_md.relative_to(ROOT)} 没有带数量列的业务域表格")

    actual = len(_actual_tool_names())
    total = sum(count for _, count in rows)
    assert total == actual, (
        f"{skill_md.relative_to(ROOT)} 业务域表格合计 {total}，代码实际 {actual} —— "
        f"逐行：{[f'{n}={c}' for n, c in rows]}"
    )
    assert len(rows) == len(_readme_domain_rows()), (
        f"{skill_md.relative_to(ROOT)} 有 {len(rows)} 个业务域，"
        f"README 有 {len(_readme_domain_rows())} 个，两份对外清单口径不一致"
    )


@pytest.mark.parametrize("skill_md", _skill_files(), ids=lambda p: p.parent.name)
def test_skill_md_keeps_unofficial_disclaimer(skill_md: Path):
    """技能商店页面属对外长文档，必须保留「第三方开源·非金蝶官方」声明。"""
    text = skill_md.read_text(encoding="utf-8")
    assert "非金蝶官方" in text, (
        f"{skill_md.relative_to(ROOT)} 缺少「非金蝶官方」声明，存在品牌争议风险"
    )
