# 金蝶云星空 MCP Server：让 Claude、Cursor 等 AI 直接操作 ERP

> 本文介绍如何通过 MCP（Model Context Protocol）协议，让 AI 助手直接操作金蝶云星空 ERP，实现采购、销售、库存等业务的自然语言自动化。

## 背景

你有没有遇到过这种场景：

- 业务人员需要查询本月采购订单，要在金蝶里点好几层菜单
- 想批量审核一批入库单，需要一条条手动操作
- 想用 AI 帮你处理 ERP 数据，但 AI 根本不认识金蝶

**金蝶 MCP Server** 就是为了解决这个问题而生的。

## 什么是 MCP？

MCP（Model Context Protocol）是 Anthropic 推出的开放协议，让 AI 助手（Claude、Cursor、Windsurf 等）可以通过标准化接口调用外部工具和服务。

简单理解：**MCP = 给 AI 装上操作外部系统的"手"**。

## 金蝶 MCP Server 能做什么？

安装后，你可以直接对 AI 说：

- "查询最近 20 条已审核的采购订单"
- "查一下物料编码 MAT001 的即时库存"
- "帮我新建一张采购订单，供应商 S001，物料 MAT001，数量 100"
- "审核这几张入库单：12345, 12346"

AI 会自动调用金蝶 WebAPI 完成操作，**无需手动登录 ERP 界面**。

## 对实施与开发的价值

**实施阶段**
- 快速验证配置：用自然语言直接查数据，无需逐层点菜单
- 数据核查：批量查询单据状态、库存数量，快速定位问题
- 客户演示：现场说"查一下你们的采购订单"，AI 实时返回结果，演示效果直观

**日常使用**
- 业务人员自助查询，减少依赖实施人员的频率
- 批量提交、审核单据，替代重复的手工操作
- 通过微信 / WhatsApp 直接操作金蝶，无需打开 ERP 客户端

**开发阶段**
- 用 `kingdee_list_forms`、`kingdee_get_fields` 快速探索表单结构，替代翻文档
- 自然语言调试接口，比手写 API 请求效率更高
- 可作为内部工具基础进行二次开发，快速扩展自定义工具

## 支持的功能

目前提供 13 个工具，覆盖核心业务场景：

**数据查询（只读）**
- 通用单据查询（支持任意 form_id）
- 查看单据详情
- 采购订单查询
- 销售订单查询
- 出入库单据查询
- 即时库存查询
- 物料档案查询
- 客户/供应商档案查询

**单据操作（写入）**
- 新建/修改单据
- 提交、审核、反审核、删除

## 支持的 AI 客户端

- **Claude Desktop**（最推荐，原生支持）
- **Cursor**（写代码的同时查 ERP 数据）
- **Windsurf**
- **Cline**
- **Continue**
- **Claude Code CLI**
- **OpenClaw**（通过微信/WhatsApp/Telegram 操作金蝶！将本项目 PyPI 地址发给 OpenClaw，它会自动完成安装并引导填写金蝶配置）

## 快速开始

### 1. 安装

```bash
pip install kingdee-mcp
```

### 2. 金蝶后台授权

进入 **系统管理 → 第三方系统登录授权 → 新增**，创建集成用户，获取 AppID 和 AppSecret。

### 3. 配置 Claude Desktop

编辑 `%APPDATA%\Claude\claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "kingdee": {
      "command": "uvx",
      "args": ["kingdee-mcp"],
      "env": {
        "KINGDEE_SERVER_URL": "http://your-server/k3cloud/",
        "KINGDEE_ACCT_ID": "你的账套ID",
        "KINGDEE_USERNAME": "集成用户名",
        "KINGDEE_APP_ID": "AppID",
        "KINGDEE_APP_SEC": "AppSecret"
      }
    }
  }
}
```

### 4. 重启客户端，开始使用

> **OpenClaw 用户**：使用 `openclaw mcp set` 配置后会自动热加载，**无需重启网关**。

## 项目地址

- GitHub：https://github.com/WaHaiLong/KingdeeMCP
- 官网文档：https://wahailong.github.io/KingdeeMCP/
- PyPI：https://pypi.org/project/kingdee-mcp/

欢迎 Star、Issues 和 PR！

---

**关键词**：金蝶MCP、金蝶云星空AI、MCP Server、金蝶ERP自动化、Claude金蝶、金蝶API集成、AI操作ERP
