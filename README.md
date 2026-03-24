# Kingdee MCP Server

金蝶云星空 ERP 的 MCP Server，让任何支持 MCP 协议的 AI 客户端都能直接操作金蝶 ERP。

支持的客户端包括：Claude Desktop、Cursor、Windsurf、Cline、Continue、Claude Code CLI、OpenClaw 等所有兼容 MCP 的应用。

通过 OpenClaw 还可以在 **WhatsApp、Telegram、微信** 等聊天应用中直接操作金蝶 ERP。

## 功能特性

- **供应链管理**: 采购订单、销售订单查询与操作
- **库存管理**: 出入库单据、即时库存查询
- **基础资料**: 物料、客户、供应商档案查询
- **单据操作**: 新建、提交、审核、反审核、删除

## 安装

```bash
pip install kingdee-mcp
```

或使用 uvx 直接运行：

```bash
uvx kingdee-mcp
```

## 配置

### 1. 金蝶云星空设置

在金蝶云星空中创建第三方系统登录授权：

1. 进入 **系统管理 → 第三方系统登录授权**
2. 新增一个集成用户，获取 **AppID** 和 **AppSecret**
3. 为该用户分配所需单据的操作权限

### 2. 配置 MCP 客户端

在你的 MCP 客户端配置文件中添加：

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

**配置文件位置：**

| 客户端 | 配置文件路径 |
|--------|-------------|
| Claude Desktop (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Cursor | Settings → MCP → Add Server |
| Claude Code CLI | `~/.claude/settings.json` |
| OpenClaw | 参考 [OpenClaw MCP 文档](https://docs.openclaw.ai/) |
| 其他客户端 | 参考对应客户端的 MCP 配置文档 |

### 3. 重启客户端

配置完成后重启你的 MCP 客户端即可使用。

## 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `KINGDEE_SERVER_URL` | 金蝶私有云地址 | `http://192.168.1.100/k3cloud/` |
| `KINGDEE_ACCT_ID` | 账套ID | `69ae8ed35dab20` |
| `KINGDEE_USERNAME` | 集成用户名 | `API集成` |
| `KINGDEE_APP_ID` | 应用ID | `338898_xxxxx` |
| `KINGDEE_APP_SEC` | 应用密钥 | `f8b75d4ccxxxx` |

## 可用工具

### 元数据查询

| 工具 | 说明 |
|------|------|
| `kingdee_list_forms` | 搜索可用表单（不知道 form_id 时用） |
| `kingdee_get_fields` | 获取表单字段列表 |

### 数据查询（只读）

| 工具 | 说明 |
|------|------|
| `kingdee_query_bills` | 通用单据查询 |
| `kingdee_view_bill` | 查看单据详情 |
| `kingdee_query_purchase_orders` | 查询采购订单 |
| `kingdee_query_sale_orders` | 查询销售订单 |
| `kingdee_query_stock_bills` | 查询出入库单据 |
| `kingdee_query_inventory` | 查询即时库存 |
| `kingdee_query_materials` | 查询物料档案 |
| `kingdee_query_partners` | 查询客户/供应商 |

### 单据操作

| 工具 | 说明 |
|------|------|
| `kingdee_save_bill` | 新建或修改单据 |
| `kingdee_submit_bills` | 提交单据 |
| `kingdee_audit_bills` | 审核单据 |
| `kingdee_unaudit_bills` | 反审核单据 |
| `kingdee_delete_bills` | 删除单据 |

## 使用示例

在 Claude 中可以使用自然语言：

- "查询最近 20 条已审核的采购订单"
- "查一下物料编码 MAT001 的即时库存"
- "查询客户编码 C001 的所有销售订单"
- "帮我新建一张采购订单，供应商 S001，物料 MAT001，数量 100"
- "审核这几张采购入库单：12345, 12346"

## 支持的单据类型

| form_id | 说明 |
|---------|------|
| `PUR_PurchaseOrder` | 采购订单 |
| `SAL_SaleOrder` | 销售订单 |
| `STK_InStock` | 采购入库 |
| `SAL_OUTSTOCK` | 销售出库 |
| `STK_MisDelivery` | 其他出库 |
| `STK_Miscellaneous` | 其他入库 |
| `STK_TransferDirect` | 直接调拨 |
| `BD_Material` | 物料档案 |
| `BD_Customer` | 客户 |
| `BD_Supplier` | 供应商 |
| `STK_Inventory` | 即时库存 |

## License

MIT
