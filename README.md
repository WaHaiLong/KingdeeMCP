<!-- mcp-name: io.github.WaHaiLong/kingdee-mcp -->

# Kingdee MCP Server —— 让 AI 直接操作金蝶云星空 ERP

[![PyPI version](https://img.shields.io/pypi/v/kingdee-mcp?style=flat-square&color=2563eb)](https://pypi.org/project/kingdee-mcp/)
[![Downloads](https://img.shields.io/pypi/dm/kingdee-mcp?style=flat-square&color=10b981)](https://pypi.org/project/kingdee-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/kingdee-mcp?style=flat-square)](https://pypi.org/project/kingdee-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)
[![MCP Badge](https://lobehub.com/badge/mcp-full/wahailong-kingdeemcp?theme=light)](https://lobehub.com/mcp/wahailong-kingdeemcp)

**Kingdee MCP Server** 是金蝶云星空（Kingdee Cloud Star）ERP 的 [MCP（Model Context Protocol）](https://modelcontextprotocol.io/) 服务端，让 Claude、Cursor、Windsurf、Cline 等 AI 助手能够通过自然语言直接操作金蝶 ERP 系统。

官方网站：https://wahailong.github.io/KingdeeMCP/

## 为什么需要金蝶 MCP？

传统 ERP 操作繁琐，需要在多个界面间切换。有了 **金蝶 MCP Server**，你可以：

- 直接对 AI 说："**查询本月已审核的采购订单**"
- 直接对 AI 说："**帮我新建一张销售订单**"
- 直接对 AI 说："**审核这几张入库单**"
- 在微信、WhatsApp、Telegram 中通过 OpenClaw 操作金蝶

AI 会自动调用金蝶 API 完成操作，无需手动登录 ERP 界面。

## 对实施与开发的价值

**实施阶段**
- **快速验证配置**：用自然语言直接查数据，无需登录 ERP 界面逐层点菜单
- **数据核查**：批量查询单据状态、库存数量，快速定位问题
- **客户演示**：现场说"查一下你们的采购订单"，AI 实时返回结果，演示效果直观

**日常使用**
- 业务人员自助查询，减少依赖实施人员的频率
- 批量提交、审核单据，替代重复的手工操作
- 通过微信 / WhatsApp 直接操作金蝶，无需打开 ERP 客户端

**开发阶段**
- 用 `kingdee_list_forms`、`kingdee_get_fields` 快速探索表单结构，替代翻文档
- 自然语言调试接口，比手写 API 请求效率更高
- 可作为内部工具基础进行二次开发，快速扩展自定义工具

## 支持的 AI 客户端

| 客户端 | 支持方式 |
|--------|---------|
| [Claude Desktop](https://claude.ai/download) | 原生 MCP |
| [Cursor](https://cursor.sh/) | 原生 MCP |
| [Windsurf](https://codeium.com/windsurf) | 原生 MCP |
| [Cline](https://github.com/cline/cline) | 原生 MCP |
| [Continue](https://continue.dev/) | 原生 MCP |
| [Claude Code CLI](https://claude.ai/claude-code) | 原生 MCP |
| [OpenClaw](https://openclaw.ai/) | 微信/WhatsApp/Telegram 中使用；将本页地址发给 OpenClaw，它会自动完成安装并引导填写金蝶配置 |
| 其他 MCP 兼容客户端 | 原生 MCP |

## 功能特性

- **87 个工具**：覆盖生产、成本、资产、审计、采购、销售、库存、财务报表等 13+ 大业务域
- **元数据动态查询**：`get_bill_template` / `validate_bill` / `refresh_metadata`，元数据本地缓存
- **4 个 SQL Server 探查工具**：搜索表、搜索字段、查看表结构、金蝶元数据候选发现
- **自然语言操作**：用中文直接描述需求，AI 自动转换为 API 调用
- **异步高性能**：基于 async/await，支持并发请求
- **自动重试**：Session 过期自动重登，连接失败自动重试
- **安全认证**：采用金蝶官方 WebAPI 认证，账号密码(ValidateUser)登录，兼容公有云和私有云，无第三方应用授权
- **类型安全**：基于 Pydantic 数据验证，参数自动补全
- **易于扩展**：基于 FastMCP 框架，轻松添加自定义工具
- **使用示例**：提供 [9 个常见业务场景示例](./examples/)，覆盖查询、新建、审核、下推等操作

## 快速安装

```bash
pip install kingdee-mcp
```

或使用 uvx 直接运行（推荐，无需手动安装）：

```bash
uvx kingdee-mcp
```

## 远程部署（HTTP / SSE 模式）

默认以 `stdio` 模式运行（本地 MCP 客户端通过子进程调用）。若要把服务部署到服务器、或用网关/托管平台（如 Smithery）**远程调用、免客户端安装**，可改用 HTTP 类传输：

```bash
# SSE 模式（兼容性好，旧客户端首选）
uvx kingdee-mcp --transport sse --host 0.0.0.0 --port 8000

# Streamable HTTP 模式（MCP 新版推荐）
uvx kingdee-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

- SSE 端点：`http://<host>:<port>/sse`
- Streamable HTTP 端点：`http://<host>:<port>/mcp`

> 远程模式下**仍需金蝶账号密码**（通过 `KINGDEE_*` 环境变量注入）。HTTP 只是传输通道，并不替代金蝶认证——客户端连上来后，工具调用照样要走金蝶 ValidateUser 登录。

也可用环境变量代替命令行参数：`KINGDEE_MCP_TRANSPORT`（stdio/sse/streamable-http）、`KINGDEE_MCP_HOST`、`KINGDEE_MCP_PORT`。

## 配置教程

### 第一步：金蝶云星空后台授权

1. 准备一个金蝶云星空账号（建议专用集成账号，**不要用 Administrator**）
2. 本服务采用**账号密码(ValidateUser)**登录，**无需**创建第三方应用、也无需 AppID / AppSecret
3. 为该账号分配所需模块的操作权限

### 第二步：配置 MCP 客户端

在你的 MCP 客户端配置文件中添加以下内容：

```json
{
  "mcpServers": {
    "kingdee": {
      "command": "uvx",
      "args": ["kingdee-mcp"],
      "env": {
        "KINGDEE_SERVER_URL": "http://your-server/k3cloud/",
        "KINGDEE_ACCT_ID": "你的账套ID",
        "KINGDEE_USERNAME": "金蝶账号",
        "KINGDEE_PASSWORD": "金蝶账号密码"
      }
    }
  }
}
```

**配置文件位置：**

| 客户端 | 配置文件路径 |
|--------|-------------|
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Cursor | Settings → MCP → Add Server |
| Claude Code CLI | `~/.claude/settings.json` |
| OpenClaw | 使用 `openclaw mcp set` 命令配置，自动热加载无需重启 |

### 第三步：重启客户端

配置完成后重启你的 MCP 客户端即可开始使用。

> **OpenClaw 用户**：使用 `openclaw mcp set` 配置后会自动热加载，**无需重启网关**。

## 环境变量说明

| 变量 | 说明 | 示例 |
|------|------|------|
| `KINGDEE_SERVER_URL` | 金蝶服务器地址（需包含 /k3cloud/） | `http://your-server/k3cloud/` |
| `KINGDEE_ACCT_ID` | 账套ID | `your-acct-id` |
| `KINGDEE_USERNAME` | 金蝶账号 | `your-username` |
| `KINGDEE_PASSWORD` | 金蝶账号密码（ValidateUser 登录，必填） | `your-password` |
| `MCP_SQLSERVER_HOST` | SQL Server 主机（可选，用于数据库探查） | `localhost` |
| `MCP_SQLSERVER_PORT` | SQL Server 端口（默认 1433） | `1433` |
| `MCP_SQLSERVER_DATABASE` | 数据库名 | `AIS20260309171043` |
| `MCP_SQLSERVER_USER` | SQL Server 用户（建议只读账号） | `sa` |
| `MCP_SQLSERVER_PASSWORD` | SQL Server 密码 | `xxxx` |

## ⚠️ 从 0.1.0 升级的破坏性变更（重要）

**0.2.0 起，登录方式从「第三方应用授权（AppID + AppSecret）」改为「账号密码（ValidateUser）」**，旧版的 `KINGDEE_APP_ID` / `KINGDEE_APP_SEC` 环境变量**已失效**。

如果你之前的 MCP 客户端配置里用的是 AppID / AppSecret，升级后会出现登录失败。请按以下方式迁移：

1. 在金蝶云星空创建一个专用集成账号（不要用 Administrator）；
2. 把 MCP 配置里的环境变量改为：**删除** `KINGDEE_APP_ID`、`KINGDEE_APP_SEC`，**新增** `KINGDEE_PASSWORD` = 该集成账号的密码；
3. 重启 MCP 客户端。

> 之所以改用账号密码，是因为账号密码(ValidateUser) 是以真实用户身份执行 WebAPI、会携带该用户自身的业务权限（含 WebApi 数据权限控制）；而第三方应用授权(LoginByAppSecret) 以应用身份登录、不携带真实用户权限，报表等依赖数据权限的查询会受应用授权范围限制，无法按用户权限正常执行。

## 可用工具列表

共 **87 个工具**，按业务域分组（每组列出代表性工具，完整清单见 `src/kingdee_mcp/server.py`）：

| 业务域 | 数量 | 代表性工具 |
|--------|------|-----------|
| 通用单据 | 10 | `kingdee_save_bill` · `kingdee_submit_bills` · `kingdee_audit_bills` · `kingdee_validate_bill` · `kingdee_push_and_audit` |
| 生产制造 | 12 | `kingdee_query_production_orders` · `kingdee_save_production_order` · `kingdee_query_mrp_result` · `kingdee_push_production_pick` |
| 成本核算 | 12 | `kingdee_query_material_cost` · `kingdee_query_cost_calculation` · `kingdee_save_cost_adjustment` · `kingdee_query_finished_product_cost` |
| 固定资产 | 6 | `kingdee_query_fixed_asset` · `kingdee_save_asset` · `kingdee_query_asset_depreciation` |
| 库存 | 9 | `kingdee_query_inventory` · `kingdee_query_stock_bills` · `kingdee_push_stock_transfer` · `kingdee_query_transfer_direct` |
| 审计合规 | 7 | `kingdee_query_operation_logs` · `kingdee_query_change_log` · `kingdee_create_and_audit` · `kingdee_push_and_audit` |
| 采购 | 4 | `kingdee_query_purchase_orders` · `kingdee_query_purchase_requisitions` · `kingdee_query_purchase_inquiry` |
| 销售 | 2 | `kingdee_query_sale_orders` · `kingdee_query_sale_quotations` |
| 工作流/审批 | 4 | `kingdee_query_pending_approvals` · `kingdee_workflow_approve` · `kingdee_query_approval_flow` |
| 基础资料/权限 | 4 | `kingdee_query_materials` · `kingdee_query_partners` · `kingdee_query_user` · `kingdee_query_role` |
| 元数据/探查 | 8 | `kingdee_get_fields` · `kingdee_list_forms` · `kingdee_get_bill_template` · `kingdee_discover_tables` |
| 系统/查询 | 4 | `kingdee_query_system_config` · `kingdee_query_quality_inspections` · `kingdee_query_expense_reimburse` |
| 统计 | 2 | `kingdee_usage_stats` · `kingdee_usage_report` |
| 财务报表 | 1 | `kingdee_query_report`（GetSysReportData 专用端点，查科目余额表/账龄分析表等总账报表） |

> 元数据探查含 4 个 SQL Server 工具（`kingdee_discover_tables` / `kingdee_discover_columns` / `kingdee_describe_table` / `kingdee_discover_metadata_candidates`），需配置 `MCP_SQLSERVER_*` 环境变量。

### 元数据查询

| 工具名称 | 功能说明 |
|----------|---------|
| `kingdee_list_forms` | 搜索可用表单（不知道 form_id 时使用） |
| `kingdee_get_fields` | 获取表单字段列表 |

### 数据查询（只读操作）

| 工具名称 | 功能说明 |
|----------|---------|
| `kingdee_query_bills` | 通用单据查询，支持任意 form_id |
| `kingdee_view_bill` | 查看单据完整详情 |
| `kingdee_query_purchase_orders` | 查询采购订单 |
| `kingdee_query_sale_orders` | 查询销售订单 |
| `kingdee_query_sale_quotations` | 查询销售报价单（SAL_Quotation） |
| `kingdee_query_stock_bills` | 查询出入库单据 |
| `kingdee_query_inventory` | 查询即时库存 |
| `kingdee_query_materials` | 查询物料档案 |
| `kingdee_query_partners` | 查询客户/供应商档案 |
| `kingdee_query_report` | 财务报表查询（GetSysReportData 专用端点）：科目余额表 `GL_RPT_AccountBalance`、账龄分析表 `GL_AgingSchedule` 等总账报表，内层过滤参数按账套透传 |

### 单据操作（写操作）

| 工具名称 | 功能说明 |
|----------|---------|
| `kingdee_save_bill` | 新建或修改单据 |
| `kingdee_submit_bills` | 提交单据 |
| `kingdee_audit_bills` | 审核单据 |
| `kingdee_unaudit_bills` | 反审核单据 |
| `kingdee_delete_bills` | 删除单据 |

## 使用示例

配置完成后，在 Claude 或其他 AI 客户端中直接用自然语言操作：

```
# 查询类
查询最近 20 条已审核的采购订单
查一下物料编码 MAT001 的即时库存
查询客户编码 C001 的所有销售订单
显示本月所有未提交的销售订单

# 操作类
帮我新建一张采购订单，供应商 S001，物料 MAT001，数量 100，单价 10.5
审核这几张采购入库单：12345, 12346, 12347
反审核销售订单 SO2024001
```

## SQL Server 探查工具（可选）

配置 `MCP_SQLSERVER_*` 环境变量后可用，帮助理解金蝶数据库结构：

| 工具名称 | 功能说明 |
|---------|---------|
| `kingdee_discover_tables` | 按关键字搜索数据库表名 |
| `kingdee_discover_columns` | 按关键字搜索字段名（含所在表） |
| `kingdee_describe_table` | 查看表完整结构（字段、类型、主键、外键） |
| `kingdee_discover_metadata_candidates` | 根据 form_id 发现对应的数据库表名 |

**典型用法**：先问 AI "采购订单在数据库里对应哪张表"，再用 `kingdee_describe_table` 看字段结构。

## 支持的单据类型（form_id）

| form_id | 说明 |
|---------|------|
| `PUR_PurchaseOrder` | 采购订单 |
| `SAL_SaleOrder` | 销售订单 |
| `STK_InStock` | 采购入库单 |
| `SAL_OUTSTOCK` | 销售出库单 |
| `STK_MisDelivery` | 其他出库单 |
| `STK_Miscellaneous` | 其他入库单 |
| `STK_TransferDirect` | 直接调拨单 |
| `BD_Material` | 物料档案 |
| `BD_Customer` | 客户档案 |
| `BD_Supplier` | 供应商档案 |
| `STK_Inventory` | 即时库存 |

## 常见问题

**Q: 提示认证失败怎么办？**
检查金蝶账号与密码(KINGDEE_PASSWORD)是否正确，该账号是否有对应模块的操作权限。

**Q: 连接超时怎么解决？**
检查 `KINGDEE_SERVER_URL` 是否正确（需包含 `/k3cloud/` 后缀），确保服务器可访问。

**Q: 支持金蝶云星空公有云吗？**
支持。公有云和私有云使用相同的账号密码(ValidateUser)认证方式，配置方式完全一致。

**Q: 用 `uvx kingdee-mcp` 启动时报 `No module named 'mcp.server.fastmcp'`？**

这是 `uvx` 的临时环境偶尔没把依赖（`mcp`）装全导致的，**不是包本身的问题**（PyPI 元数据已正确声明 `mcp[cli]>=1.0.0`）。两种解决方式：

1. 清理 uv 缓存后重试：`uv cache clean`，再重新启动 `uvx kingdee-mcp`；
2. 或改用 pip 安装 + 模块方式启动（更稳，推荐用于生产）：

   ```bash
   pip install kingdee-mcp
   ```

   MCP 客户端配置改为：

   ```json
   {
     "mcpServers": {
       "kingdee": {
         "command": "python",
         "args": ["-m", "kingdee_mcp.server"],
         "env": { "KINGDEE_SERVER_URL": "...", "KINGDEE_ACCT_ID": "...", "KINGDEE_USERNAME": "...", "KINGDEE_PASSWORD": "..." }
       }
     }
   }
   ```

## 配合 mcp-sqlserver-introspect 使用

kingdee-mcp 提供两层能力：

**第一层：ERP 操作层**（kingdee-mcp 内置）
直接操作金蝶单据：查询、新建、提交、审核、下推等。

**第二层：数据库理解层**（mcp-sqlserver-introspect）
探查 SQL Server 表结构：找表、找字段、理解关联关系。

**典型使用场景**：

```
# 场景一：接口映射
问："帮我找采购订单相关的表"
→ mcp-sqlserver-introspect 返回 T_PUR_PurchaseOrder 等表
→ 确认 Kingdee API 字段和数据库字段的对应关系

# 场景二：字段溯源
问："帮我查 FTotalAmount 这个字段在哪些表里"
→ mcp-sqlserver-introspect 返回包含该字段的表列表

# 场景三：数据核查
先用 mcp-sqlserver-introspect 探索表结构
再用 kingdee-mcp 操作 ERP 数据
两者配合，AI 既能理解数据库，又能操作 ERP
```

**mcp-sqlserver-introspect** 项目地址：https://gitee.com/lzhrick123/mcp-sqlserver-introspect1

> kingdee-mcp 已内置 SQL Server 探查工具（配置 `MCP_SQLSERVER_*` 环境变量即可使用），无需额外安装 mcp-sqlserver-introspect。

**Q: 如何添加自定义工具？**
基于 FastMCP 框架，在 `server.py` 中添加 `@mcp.tool()` 装饰器方法即可扩展。

## 相关链接

- [官方网站](https://wahailong.github.io/KingdeeMCP/)
- [PyPI 包页面](https://pypi.org/project/kingdee-mcp/)
- [MCP 协议文档](https://modelcontextprotocol.io/)
- [金蝶云星空官网](https://www.kingdee.com/)

## 联系方式

- QQ：1724349716
- 邮箱：1724349716@qq.com

## License

MIT © WaHaiLong
