"""端到端 smoke：登录 + 查询销售订单。

凭证由环境变量提供（参考 CLAUDE.md：本地存于 C:\\Users\\ZnL\\kingdee-mcp.bat）。
未配置 KINGDEE_* 时由 conftest 静默跳过。
"""
import pytest

import kingdee_mcp.server as srv

pytestmark = pytest.mark.e2e


async def test_login_and_query_sale_orders():
    await srv._login()

    payload = srv._query_payload(
        "SAL_SaleOrder",
        "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName",
        "",
        "FDate DESC",
        0,
        20,
    )
    rows = srv._rows(await srv._post("query", payload))

    assert isinstance(rows, list)
    if rows:
        first = rows[0]
        assert len(first) >= 5, f"expected 5 columns, got {len(first)}: {first}"
