"""
pytest 配置：集成测试需要真实金蝶服务器
没有配置环境变量时跳过集成测试
"""

import os
import pytest

# 检查是否有真实服务器配置
HAS_KINGDEE_CONFIG = bool(
    os.getenv("KINGDEE_SERVER_URL") and
    os.getenv("KINGDEE_ACCT_ID") and
    os.getenv("KINGDEE_USERNAME") and
    os.getenv("KINGDEE_APP_ID") and
    os.getenv("KINGDEE_APP_SEC")
)


def pytest_collection_modifyitems(config, items):
    """集成测试（test_integration.py）在没有真实配置时跳过"""
    for item in items:
        if "test_integration" in item.nodeid:
            if not HAS_KINGDEE_CONFIG:
                item.add_marker(pytest.mark.skip(
                    reason="需要真实金蝶服务器环境变量（KINGDEE_SERVER_URL 等），当前未配置"
                ))