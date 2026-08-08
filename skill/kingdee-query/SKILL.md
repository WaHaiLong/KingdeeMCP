---
name: kingdee-query
slug: kingdee-query
displayName: 金蝶云星空查询与操作助手
version: 1.0.0
description: 基于已连接的 kingdee-mcp（第三方开源金蝶云星空 MCP 服务器，非金蝶官方出品），用自然语言查询与操作金蝶 ERP：销售/采购订单、即时库存、物料档案、客户/供应商、单据提交/审核/下推、生产/成本/资产等。当用户提到"金蝶""查金蝶""金蝶销售订单/库存/物料"等 ERP 查询或操作需求时触发。
---

# 金蝶云星空 查询与操作助手 (kingdee-query)

> 本技能**不自己连接金蝶**，它只是"导航员"：依赖名为 `kingdee` 的 MCP 服务器已在 WorkBuddy 中连接，并把用户的自然语言翻译成 kingdee-mcp 的工具调用。

## 一、前置条件（务必先确认）

- 入口：WorkBuddy 左侧 **插件 → MCP 服务器 → 配置 MCP**，确认 `kingdee` 已添加且状态为已连接（工具列表正常加载）。
- 必需环境变量：
  - `KINGDEE_SERVER_URL`：金蝶服务器地址，**必须包含 `/k3cloud/`** 后缀
  - `KINGDEE_ACCT_ID`：账套 ID
  - `KINGDEE_USERNAME`：金蝶账号（建议专用集成账号，不要 Administrator）
  - `KINGDEE_PASSWORD`：账号密码（ValidateUser 登录，**必填**）
- 可选：
  - `KINGDEE_LCID`：语言区，默认 `2052`（简体中文）
  - `MCP_SQLSERVER_*`：SQL Server 主机/端口/库/账号，启用数据库探查工具
- 认证方式：金蝶 WebAPI **账号密码(ValidateUser)**，无需 AppID / AppSecret。
- 若尚未配置，请把仓库 `examples/workbuddy-mcp-config.example.json` 中的 `kingdee` 片段加入用户级 `~/.workbuddy/mcp.json`（替换占位符），重启 WorkBuddy 后再用本技能。

## 二、触发示例

- "查一下本月已审核的销售订单"
- "物料 MAT001 的即时库存是多少"
- "显示客户 C001 的所有销售订单"
- "帮我新建一张采购订单，供应商 S001，物料 MAT001，数量 100，单价 10.5"
- "审核这几张采购入库单：12345, 12346, 12347"
- "采购订单在数据库里对应哪张表"（需配置 MCP_SQLSERVER_*）

## 三、可用工具（kingdee-mcp，共 86 个，按业务域）

| 业务域 | 代表性工具 | 说明 |
|--------|-----------|------|
| 通用单据 | `kingdee_save_bill` · `kingdee_submit_bills` · `kingdee_audit_bills` · `kingdee_validate_bill` · `kingdee_push_and_audit` | 新建/提交/审核/下推 |
| 生产制造 | `kingdee_query_production_orders` · `kingdee_save_production_order` · `kingdee_query_mrp_result` | 生产订单、MRP |
| 成本核算 | `kingdee_query_material_cost` · `kingdee_query_cost_calculation` · `kingdee_save_cost_adjustment` | 材料成本、成本计算 |
| 固定资产 | `kingdee_query_fixed_asset` · `kingdee_save_asset` · `kingdee_query_asset_depreciation` | 资产卡片、折旧 |
| 库存 | `kingdee_query_inventory` · `kingdee_query_stock_bills` · `kingdee_push_stock_transfer` | 即时库存、出入库 |
| 审计合规 | `kingdee_query_operation_logs` · `kingdee_query_change_log` · `kingdee_create_and_audit` | 操作/变更日志 |
| 采购 | `kingdee_query_purchase_orders` · `kingdee_query_purchase_requisitions` | 采购订单/申请 |
| 销售 | `kingdee_query_sale_orders` · `kingdee_query_sale_quotations` | 销售订单/报价 |
| 工作流 | `kingdee_query_pending_approvals` · `kingdee_workflow_approve` | 待审/审批 |
| 基础资料 | `kingdee_query_materials` · `kingdee_query_partners` · `kingdee_query_user` | 物料/往来/用户 |
| 元数据探查 | `kingdee_list_forms` · `kingdee_get_fields` · `kingdee_get_bill_template` · `kingdee_discover_tables` | 表单/字段/库表 |
| 系统/统计 | `kingdee_query_system_config` · `kingdee_usage_stats` · `kingdee_usage_report` | 配置/用量 |

> 完整 86 个工具见 `src/kingdee_mcp/server.py`。元数据探查含 4 个 SQL Server 工具（`kingdee_discover_tables` / `kingdee_discover_columns` / `kingdee_describe_table` / `kingdee_discover_metadata_candidates`），需配置 `MCP_SQLSERVER_*`。

## 四、使用约定

1. **先探查后查询**：不知道 `form_id` 时，用 `kingdee_list_forms` 搜索表单、用 `kingdee_get_fields` 取字段；通用查询用 `kingdee_query_bills`（需传 `form_id`）。
2. **只读优先**：查询用 `kingdee_query_*` 系列；看单据全貌用 `kingdee_view_bill`。
3. **写操作谨慎**：`kingdee_save_bill` / `kingdee_submit_bills` / `kingdee_audit_bills` / `kingdee_push_and_audit` 等会改动 ERP 数据，执行前必须与用户确认关键参数（单据类型、数量/金额、目标单号），必要时二次确认。
4. **中文呈现**：结果用中文结构化输出（表格/要点），金额、数量、日期等保留原值并注明单位。
5. **错误处理**：登录失败多为账号无权限或密码错误；连接超时先检查 `KINGDEE_SERVER_URL` 是否含 `/k3cloud/`。

## 五、常见 form_id 速查

`PUR_PurchaseOrder` 采购订单 · `SAL_SaleOrder` 销售订单 · `STK_InStock` 采购入库单 · `SAL_OUTSTOCK` 销售出库单 · `STK_TransferDirect` 直接调拨单 · `STK_Inventory` 即时库存 · `BD_Material` 物料 · `BD_Customer` 客户 · `BD_Supplier` 供应商

## 六、依赖

- 本技能依赖 **kingdee-mcp** MCP 服务器（PyPI：`pip install kingdee-mcp`，或 `uvx kingdee-mcp`）。
- 安装与配置见仓库根目录 `README.md` 与 `PUBLISH.md`。
