"""
pytest 配置：集成 + 端到端测试需要真实金蝶服务器
没有配置环境变量时静默跳过
"""

import os
import pytest

HAS_KINGDEE_CONFIG = bool(
    os.getenv("KINGDEE_SERVER_URL") and
    os.getenv("KINGDEE_ACCT_ID") and
    os.getenv("KINGDEE_USERNAME") and
    os.getenv("KINGDEE_APP_ID") and
    os.getenv("KINGDEE_APP_SEC")
)


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: 真实金蝶环境的端到端测试（需 KINGDEE_* 环境变量）")


def pytest_collection_modifyitems(config, items):
    """test_integration.py 与 tests/e2e/ 在无真实配置时跳过"""
    skip_reason = "需要真实金蝶服务器环境变量（KINGDEE_SERVER_URL 等），当前未配置"
    needs_real = ("test_integration", "tests/e2e", "tests\\e2e")
    for item in items:
        if any(key in item.nodeid for key in needs_real):
            if not HAS_KINGDEE_CONFIG:
                item.add_marker(pytest.mark.skip(reason=skip_reason))