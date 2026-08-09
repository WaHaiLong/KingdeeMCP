"""
FORM_CATALOG 中 db_tables（主表 + 分录表）命名一致性回归测试

背景（issue #13）：
    采购订单曾被写成 ("T_PUR_PURCHASEORDER", "T_PUR_POORDERENTRY")，
    主表与分录表前缀自相矛盾 —— 分录表叫 T_PUR_POORDER**ENTRY**，
    说明主表必然是 T_PUR_POORDER，而不是 T_PUR_PURCHASEORDER。
    该错误表名会被喂给 AI 用于生成 SQL，直接导致用户侧「对象名无效」。

金蝶云星空的物理表命名约定：
    分录表 = 主表名 + ENTRY / DETAIL 之类的后缀。
    因此只要分录表名不以主表名打头，就一定有一边写错了。
    这条规则是纯机械校验，不需要连真机账套，可以永久防住这类回归。

例外：
    TRNV_* 是客户自定义单据（表名形如 TRNV_t_Cust100002 / TRNV_t_Cust_Entry100007），
    走金蝶动态表命名，不适用上述约定，显式白名单放行。
"""

import pytest

from kingdee_mcp.server import FORM_CATALOG

# 自定义单据：表名由 BOS 动态生成，不遵循「主表名 + ENTRY」约定
CUSTOM_FORM_PREFIXES = ("TRNV_",)


def _paired_entries():
    """产出所有「主表 + 分录表」成对定义的业务对象。"""
    for form_id, meta in FORM_CATALOG.items():
        tables = meta.get("db_tables") or ()
        if len(tables) >= 2:
            yield form_id, tables


def test_db_tables_pairs_exist():
    """至少要有成对定义的对象，否则说明本测试的取数逻辑已失效。"""
    pairs = list(_paired_entries())
    assert len(pairs) > 20, f"成对 db_tables 只找到 {len(pairs)} 条，取数逻辑可能已失效"


@pytest.mark.parametrize("form_id,tables", list(_paired_entries()))
def test_entry_table_prefixed_by_main_table(form_id, tables):
    """分录表名必须以主表名开头，否则主表名八成写错了（见 issue #13）。"""
    if form_id.startswith(CUSTOM_FORM_PREFIXES):
        pytest.skip(f"{form_id} 为自定义单据，表名由 BOS 动态生成，不适用命名约定")

    main, entry = tables[0], tables[1]
    assert entry.upper().startswith(main.upper()), (
        f"{form_id} 的主表/分录表前缀对不上：\n"
        f"    主表   = {main}\n"
        f"    分录表 = {entry}\n"
        f"分录表名通常是「主表名 + ENTRY」，据此推断主表应为 "
        f"{entry[:-5] if entry.upper().endswith('ENTRY') else '???'}。\n"
        f"错误表名会让 AI 生成查不到的 SQL，请核对后修正。"
    )


def test_pur_purchaseorder_regression():
    """issue #13 定向回归：采购订单主表必须是 T_PUR_POORDER。"""
    tables = FORM_CATALOG["PUR_PurchaseOrder"]["db_tables"]
    assert tables[0] == "T_PUR_POORDER", (
        f"采购订单主表被改回了 {tables[0]}；"
        f"同文件内 T_PUR_POORDERENTRY / T_PUR_POORDERINSTALLMENT 均可佐证正确值为 T_PUR_POORDER"
    )
