# 金蝶云星空 MCP Server — Agent 接口调用文档

> 本文档面向 AI Agent（Claude 等 LLM Agent），说明如何通过 MCP 工具操作金蝶 ERP。
> 底层接口为金蝶 K/3 Cloud WebAPI（v8.2.886.8），通过 FastMCP 暴露为 33 个工具：
> 31 个原子工具 + 2 个复合工具（`kingdee_create_and_audit` / `kingdee_push_and_audit`）。
> **优先用复合工具完成"一条龙"创建/下推流程，可避免漏掉 Submit/Audit 造成的目标漂移。**

---

## 目录

1. [环境配置](#1-环境配置)
2. [工具速查表](#2-工具速查表)
3. [核心概念](#3-核心概念)
4. [查询类工具](#4-查询类工具)
5. [写入类工具](#5-写入类工具)
6. [下推类工具](#6-下推类工具)
7. [元数据工具](#7-元数据工具)
8. [SQL 探查工具](#8-sql-探查工具)
9. [审批流工具](#9-审批流工具)
10. [常见陷阱与注意事项](#10-常见陷阱与注意事项)
11. [完整调用流程示例](#11-完整调用流程示例)

---

## 1. 环境配置

### 必需环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `KINGDEE_SERVER_URL` | 服务器地址，结尾必须是 `/k3cloud/` | `http://wcl/k3cloud/` |
| `KINGDEE_ACCT_ID` | 账套 ID | `69ae8ed35dab20` |
| `KINGDEE_USERNAME` | 集成用户名 | `demo` |
| `KINGDEE_APP_ID` | App ID（管理员在金蝶平台创建） | `338898_x+bC0di...` |
| `KINGDEE_APP_SEC` | App Secret | `f8b75d4cc5484c...` |
| `KINGDEE_LCID` | 语言标识（可选，默认 2052=简体中文） | `2052` |

### 可选：SQL Server 探查

| 变量 | 说明 |
|------|------|
| `MCP_SQLSERVER_HOST` | SQL Server 主机名 |
| `MCP_SQLSERVER_PORT` | 端口，默认 1433 |
| `MCP_SQLSERVER_DATABASE` | 数据库名，如 `AIS20260309171043` |
| `MCP_SQLSERVER_USER` | 用户名 |
| `MCP_SQLSERVER_PASSWORD` | 密码 |

> **Demo 环境**：`http://wcl/k3cloud/`，账套 `69ae8ed35dab20`，用户 `demo`

---

## 2. 工具速查表

### 查询类（只读）

| 工具名 | 用途 | 关键参数 |
|--------|------|---------|
| `kingdee_query_bills` | 通用单据查询（任意 form_id） | `form_id`, `filter_string`, `field_keys` |
| `kingdee_query_purchase_orders` | 采购订单列表（快捷工具） | `filter_string` |
| `kingdee_query_purchase_order_progress` | 采购订单执行进度（含分录明细） | `filter_string` |
| `kingdee_query_sale_orders` | 销售订单列表 | `filter_string` |
| `kingdee_query_stock_bills` | 出入库单据（指定 form_id） | `form_id`, `filter_string` |
| `kingdee_query_inventory` | 即时库存（STK_Inventory） | `filter_string` |
| `kingdee_query_materials` | 物料基础资料（BD_Material） | `filter_string` |
| `kingdee_query_partners` | 客户或供应商 | `partner_type`, `filter_string` |
| `kingdee_view_bill` | 查看单据完整详情（按 FID） | `form_id`, `bill_id` |
| `kingdee_query_purchase_requisitions` | 采购申请单 | `filter_string` |
| `kingdee_query_sale_quotations` | 销售报价单 | `filter_string` |

### 写入类（原子）

| 工具名 | 用途 | 关键参数 |
|--------|------|---------|
| `kingdee_save_bill` | 新建或修改单据 | `form_id`, `model` |
| `kingdee_submit_bills` | 提交单据（草稿→待审核） | `form_id`, `bill_ids` |
| `kingdee_audit_bills` | 审核单据（待审核→已审核） | `form_id`, `bill_ids` |
| `kingdee_unaudit_bills` | 反审核（已审核→待审核） | `form_id`, `bill_ids` |
| `kingdee_delete_bills` | 删除单据（仅草稿） | `form_id`, `bill_ids` |
| `kingdee_push_bill` | 下推生成目标单据 | `form_id`, `target_form_id`, `source_bill_nos` |

### 写入类（复合 / 推荐）

| 工具名 | 内部链路 | 关键参数 |
|--------|----------|---------|
| `kingdee_create_and_audit` | save → submit → audit | `form_id`, `model` |
| `kingdee_push_and_audit` | push → submit → audit (目标单) | `form_id`, `target_form_id`, `source_bill_nos`, `rule_id` |

### 元数据类

| 工具名 | 用途 |
|--------|------|
| `kingdee_list_forms` | 搜索可用表单（按关键字） |
| `kingdee_get_fields` | 获取表单字段及业务规则 |

### SQL 探查类

| 工具名 | 用途 |
|--------|------|
| `kingdee_discover_tables` | 按关键字搜索数据库表 |
| `kingdee_discover_columns` | 按关键字搜索数据库字段 |
| `kingdee_describe_table` | 查看表完整结构 |
| `kingdee_discover_metadata_candidates` | form_id → 数据库表名映射发现 |

### 审批流类

| 工具名 | 用途 |
|--------|------|
| `kingdee_query_pending_approvals` | 查询待审批单据 |
| `kingdee_query_workflow_status` | 查询单据审批状态 |
| `kingdee_workflow_approve` | 审批通过或驳回 |
| `kingdee_query_expense_reimburse` | 查询费用报销单 |

---

## 3. 核心概念

### 3.1 form_id 是什么

`form_id` 是金蝶单据的内部标识符，AI 不知道 form_id 时，先调用 `kingdee_list_forms` 搜索：

```
kingdee_list_forms({ keyword: "采购订单" })
// 返回: form_id = "PUR_PurchaseOrder"
```

常用 form_id：

| form_id | 单据名称 |
|---------|---------|
| `PUR_PurchaseOrder` | 采购订单 |
| `SAL_SaleOrder` | 销售订单 |
| `STK_InStock` | 采购入库单 |
| `SAL_OUTSTOCK` | 销售出库单 |
| `BD_Material` | 物料 |
| `BD_Supplier` | 供应商 |
| `BD_Customer` | 客户 |
| `STK_Inventory` | 即时库存 |
| `ER_ExpenseReimburse` | 费用报销单 |

### 3.2 FID vs FBillNo

- **FID**：单据内码，数字字符串，如 `"100012"`，用于 API 操作（提交/审核/删除）
- **FBillNo**：单据编号，如 `"CGRK2026030012"`，用户可见，用于下推时指定源单据

### 3.3 单据状态枚举

| 状态码 | 含义 | 说明 |
|--------|------|------|
| `A` | 创建 | 草稿，可编辑/删除 |
| `B` | 审核中 | 已提交，待审核 |
| `C` | 已审核 | 最终状态，可下推 |
| `D` | 重新审核 | 被驳回，需重新提交 |
| `Z` | 暂存 | 临时状态，无编号 |

### 3.4 关联字段格式

Kingdee API 中关联其他基础资料的字段使用嵌套对象：

```json
// 按编码关联（推荐）
{ "FSupplierId": { "FNumber": "S001" } }
{ "FMaterialId": { "FNumber": "MAT001" } }

// 按名称关联（不推荐，可能不精确）
{ "FSupplierId": { "FName": "华强物资" } }
```

### 3.5 分录字段命名规律

单据分录（表体行）字段通常以 `F` + 分录名 + `_` 开头：

| 单据 | 分录名 | 分录字段前缀 |
|------|--------|------------|
| 采购订单 | 采购订单分录 | `FPOOrderEntry_` |
| 销售订单 | 销售订单分录 | `FSALORDERENTRY_` |
| 采购入库单 | 采购入库分录 | `FSTKINSTOCKENTRY_` |

> **注意**：分录字段在 Query 和 Save 中格式不同：
> - Query：`FMaterialId.FName`（跨表取名字）
> - Save：`FMaterialId: {FNumber: "..."}`（嵌套对象）

---

## 4. 查询类工具

### 4.1 kingdee_query_bills（通用查询）

最通用的查询工具，可查任意 form_id。

```json
{
  "tool": "kingdee_query_bills",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "filter_string": "FDocumentStatus='C' and FDate>='2026-01-01'",
    "field_keys": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FTaxAmount",
    "order_string": "FDate DESC",
    "start_row": 0,
    "limit": 20
  }
}
```

**filter_string 常用写法**：

| 目的 | filter_string |
|------|--------------|
| 已审核 | `FDocumentStatus='C'` |
| 指定供应商 | `FSupplierId.FNumber='S001'` |
| 指定日期范围 | `FDate>='2026-01-01' and FDate<='2026-01-31'` |
| 未关闭 | `FCloseStatus='A'` |
| 金额大于 | `FTaxAmount>10000` |
| 按编号模糊 | `FBillNo like 'CG%'` |
| 按名称模糊 | `FSupplierId.FName like '%华强%'` |

**field_keys 说明**：
- 用逗号分隔字段名
- 关联字段用 `.FName` 取名称、`.FNumber` 取编码
- `*` 表示全部字段（不推荐，数据量大）

### 4.2 kingdee_query_purchase_order_progress（执行进度）

专用于采购订单，返回分录级明细（每行物料的执行情况）：

```json
{
  "tool": "kingdee_query_purchase_order_progress",
  "params": {
    "filter_string": "FDocumentStatus='C'",
    "start_row": 0,
    "limit": 20
  }
}
```

返回字段：`FID, FBillNo, FMaterialId.FNumber, FMaterialId.FName, FQty, FReceiveQty, FStockInQty, FPrice, FTaxPrice, FAllAmount`

**Demo 环境注意**：以下字段不存在，用 `FReceiveQty + FStockInQty` 代替：

| 字段 | 说明 |
|------|------|
| `FLinkQty` | 关联数量 |
| `FBusinessClose` | 业务关闭状态 |
| `FFreezeStatus` | 冻结状态 |
| `FTerminateStatus` | 终止状态 |
| `FDlyCntl_Low` | 交货下限 |
| `FDlyCntl_High` | 交货上限 |

### 4.3 kingdee_view_bill（查看单据详情）

根据 FID 获取单据完整内容（含所有分录字段）：

```json
{
  "tool": "kingdee_view_bill",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "bill_id": "100012"
  }
}
```

返回结构有双层嵌套：`result["Result"]["Result"]` 才是实际单据数据。

### 4.4 kingdee_query_inventory（即时库存）

```json
{
  "tool": "kingdee_query_inventory",
  "params": {
    "filter_string": "FMaterialId.FNumber='MAT001' and FBaseQty>0",
    "field_keys": "FMaterialId.FNumber,FMaterialId.FName,FStockId.FName,FBaseQty,FBaseUnitId.FName",
    "start_row": 0,
    "limit": 20
  }
}
```

### 4.5 kingdee_query_materials（物料查询）

```json
{
  "tool": "kingdee_query_materials",
  "params": {
    "filter_string": "FNumber like 'HG%' and FDocumentStatus='C'",
    "field_keys": "FMaterialId,FNumber,FName,FSpecification,FUnitId.FName,FMaterialGroup.FName",
    "start_row": 0,
    "limit": 20
  }
}
```

---

## 5. 写入类工具

### 5.1 kingdee_save_bill（新建/修改）

**新建（不传 FID）**：

```json
{
  "tool": "kingdee_save_bill",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "model": {
      "FDate": "2026-04-10",
      "FSupplierId": { "FNumber": "S001" },
      "FPurchaseDeptId": { "FNumber": "D001" },
      "FPurchaserId": { "FNumber": "EMP001" },
      "FPOOrderEntry": [
        {
          "FMaterialId": { "FNumber": "MAT001" },
          "FQty": 100,
          "FPrice": 50,
          "FTaxRate": 13,
          "FUnitID": { "FNumber": "PCS" }
        }
      ]
    },
    "need_update_fields": [],
    "is_delete_entry": true
  }
}
```

**修改（必须传 FID）**：

```json
{
  "tool": "kingdee_save_bill",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "model": {
      "FID": "100012",
      "FPOOrderEntry": [
        { "FPOOrderEntry_LineId": "100012-element-1", "FQty": 150 }
      ]
    },
    "need_update_fields": ["FPOOrderEntry_FQty"],
    "is_delete_entry": false
  }
}
```

**返回结果解析**：

```json
{
  "Result": {
    "FID": "100012",
    "FBillNo": "CGRK2026040012",
    "ResponseStatus": { "IsSuccess": true, "Errors": [] }
  }
}
```

Save 可能返回以下三种格式，AI 需要全部兼容：

| 路径 | 字段名 |
|------|--------|
| `Result.FID` | FID（部分接口） |
| `Result.Id` | Id（同 FID，部分接口） |
| `Result.SuccessEntitys[0].Id` | FID（标准格式） |
| `Result.FBillNo` | 单据编号 |
| `Result.Number` | 单据编号（部分接口别名） |

### 5.2 kingdee_submit_bills（提交）

新建的单据（状态 Z）需要先提交，才能审核：

```json
{
  "tool": "kingdee_submit_bills",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "bill_ids": ["100012"]
  }
}
```

### 5.3 kingdee_audit_bills（审核）

提交后的单据（状态 B）可以审核：

```json
{
  "tool": "kingdee_audit_bills",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "bill_ids": ["100012"]
  }
}
```

**快捷操作（提交+审核）**：

```
1. kingdee_save_bill     → 新建单据，拿回 FID
2. kingdee_submit_bills → 提交
3. kingdee_audit_bills   → 审核
```

### 5.4 kingdee_unaudit_bills（反审核）

已审核单据（状态 C）可以反审核回待审核状态（状态 B）：

```json
{
  "tool": "kingdee_unaudit_bills",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "bill_ids": ["100012"]
  }
}
```

**反审核限制**：
- 采购订单被付款单关联后，不可反审核
- 下游已生成入库单时，可能无法反审核

### 5.5 kingdee_delete_bills（删除）

仅草稿状态（A）或暂存状态（Z）的单据可以删除：

```json
{
  "tool": "kingdee_delete_bills",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "bill_ids": ["100012"]
  }
}
```

### 5.6 kingdee_create_and_audit（一站式创建并审核 / 推荐）

将 `save → submit → audit` 三步合并到单次调用，避免 AI 漏掉中间步骤造成的目标漂移。

```json
{
  "tool": "kingdee_create_and_audit",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "model": {
      "FDate": "2026-04-30",
      "FSupplierId": { "FNumber": "S001" },
      "FPurchaseDeptId": { "FNumber": "D001" },
      "FPOOrderEntry": [
        { "FMaterialId": { "FNumber": "MAT001" }, "FQty": 100, "FPrice": 50 }
      ]
    }
  }
}
```

**返回结构**（成功）：

```json
{
  "op": "create_and_audit",
  "success": true,
  "halted_at": null,
  "steps": [
    { "op": "save",   "success": true, "fid": "100105", "bill_no": "CGDD2026040105" },
    { "op": "submit", "success": true },
    { "op": "audit",  "success": true }
  ],
  "fid": "100105",
  "bill_no": "CGDD2026040105",
  "next_action": null,
  "tip": "工作流完成，单据已审核生效..."
}
```

**halt-on-failure**：任意一步失败立即停止，不自动重试。失败响应会提供 `halted_at` 和 `recovery_hint`：

```json
{
  "op": "create_and_audit",
  "success": false,
  "halted_at": "submit",
  "fid": "100105",
  "errors": [{ "message": "...", "matched": { "next_action_tool": "kingdee_get_fields", ... } }],
  "recovery_hint": "草稿已生成 (fid=100105)。Submit 失败：检查 errors[].matched.suggestion。修正后调用 kingdee_submit_bills(form_id=\"PUR_PurchaseOrder\", bill_ids=[\"100105\"]) 重试。"
}
```

**何时改用手工链路**：需要在中间步骤做自定义校验、逐张人工 review、或针对失败做特殊清理时。

---

## 6. 下推类工具

### 6.1 kingdee_push_bill

将源单据下推生成目标单据，如销售订单→出库单、采购订单→入库单。

**基础用法（生产环境）**：

```json
{
  "tool": "kingdee_push_bill",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "target_form_id": "STK_InStock",
    "source_bill_nos": ["CGDD000025"]
  }
}
```

**Demo 环境（必须指定 rule_id）**：

```json
{
  "tool": "kingdee_push_bill",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "target_form_id": "STK_InStock",
    "source_bill_nos": ["CGDD000025"],
    "rule_id": "PUR_PurchaseOrder-STK_InStock"
  }
}
```

**强制使用默认规则**：

```json
{
  "tool": "kingdee_push_bill",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "target_form_id": "STK_InStock",
    "source_bill_nos": ["CGDD000025"],
    "enable_default_rule": true
  }
}
```

**常用下推场景**：

| 场景 | form_id | target_form_id |
|------|---------|----------------|
| 销售订单→出库单 | `SAL_SaleOrder` | `SAL_OUTSTOCK` |
| 采购订单→入库单 | `PUR_PurchaseOrder` | `STK_InStock` |
| 采购订单→收料通知 | `PUR_PurchaseOrder` | `PUR_ReceiveBill` |
| 销售订单→退货单 | `SAL_SaleOrder` | `SAL_RETURNSTOCK` |
| 采购申请→采购订单 | `PUR_Requisition` | `PUR_PurchaseOrder` |

**rule_id 未知时**：查询 `T_META_CONVERTRULE` SQL 表获取。

**返回结果**：

```json
{
  "Result": {
    "ResponseStatus": { "IsSuccess": true, "Errors": [] },
    "Ids": ["300001"],
    "Numbers": ["XSCKD2026030001"]
  }
}
```

下推后目标单据状态为「暂存」或「创建」，需要提交+审核。

**下推失败的常见原因**：

| 原因 | 说明 |
|------|------|
| 源单据未审核 | 必须 `FDocumentStatus='C'` |
| 关联数量已满 | `FLinkQty >= FQty` 无法再下推 |
| 单据已关闭 | `FCloseStatus='B'` |
| 业务关闭 | `FBusinessClose='B'` |
| 冻结/终止 | 分录被冻结或终止 |
| rule_id 错误 | Demo 环境无默认规则，需显式指定 |

### 6.2 kingdee_push_and_audit（一站式下推并审核 / 推荐）

在 `kingdee_push_bill` 之上自动 Submit + Audit 所有生成的目标草稿单。

```json
{
  "tool": "kingdee_push_and_audit",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "target_form_id": "STK_InStock",
    "source_bill_nos": ["CGDD2026040105"],
    "rule_id": "PUR_PurchaseOrder-STK_InStock"
  }
}
```

**参数说明**：

| 参数 | 默认 | 说明 |
|------|------|------|
| `auto_submit_audit` | `true` | 设为 `false` 时退化为纯 push（目标单留为草稿） |
| `enable_default_rule` | `false` | 生产环境通常用此模式（无需 rule_id） |
| `rule_id` | `""` | Demo 环境必填 |
| `draft_on_fail` | `false` | 保存失败时目标单暂存（无单据编号） |

**返回结构**（成功）：

```json
{
  "op": "push_and_audit",
  "success": true,
  "halted_at": null,
  "source_bill_nos": ["CGDD2026040105"],
  "target_form_id": "STK_InStock",
  "target_bill_nos": ["CGRKD2026040015"],
  "target_fids": ["300015"],
  "steps": [
    { "op": "push",   "success": true, "target_bill_nos": ["..."], "target_fids": ["..."] },
    { "op": "submit", "success": true },
    { "op": "audit",  "success": true }
  ],
  "next_action": null
}
```

halt-on-failure 语义同 `kingdee_create_and_audit`，失败响应携带 `halted_at` + `recovery_hint`。

---

## 7. 元数据工具

### 7.1 kingdee_list_forms（搜索表单）

不知道 form_id 时使用：

```json
{
  "tool": "kingdee_list_forms",
  "params": { "keyword": "采购" }
}
```

返回每个表单的：form_id、name、alias、desc、recommended_fields、db_tables

### 7.2 kingdee_get_fields（获取字段详情）

```json
{
  "tool": "kingdee_get_fields",
  "params": { "form_id": "PUR_PurchaseOrder" }
}
```

返回：recommended_fields、field_list、business_rules（关键业务规则）

**Demo 环境注意**：以下字段不存在于采购订单中：

```
FLinkQty, FBusinessClose, FFreezeStatus, FTerminateStatus,
FDlyCntl_Low, FDlyCntl_High, FCloseStatus, FTotalAmount
```

---

## 8. SQL 探查工具

> 需要配置 `MCP_SQLSERVER_*` 环境变量。仅查系统目录，不读业务数据。

### 8.1 kingdee_discover_tables（搜索表）

```json
{
  "tool": "kingdee_discover_tables",
  "params": { "pattern": "purchase", "limit": 20 }
}
```

### 8.2 kingdee_discover_columns（搜索字段）

```json
{
  "tool": "kingdee_discover_columns",
  "params": { "pattern": "supplier", "limit": 30 }
}
```

### 8.3 kingdee_describe_table（表结构）

```json
{
  "tool": "kingdee_describe_table",
  "params": { "table_name": "T_PUR_PURCHASEORDER" }
}
```

**Demo 环境表名规范**：全部大写，不带 `t_` 前缀：
- `T_PUR_PURCHASEORDER`（不是 `t_PUR_PurchaseOrder`）
- `T_BD_MATERIAL`
- `T_STK_INSTOCK`

### 8.4 kingdee_discover_metadata_candidates（form_id → 表名）

```json
{
  "tool": "kingdee_discover_metadata_candidates",
  "params": { "form_id": "PUR_PurchaseOrder", "limit": 10 }
}
```

返回该 form_id 对应的主表和分录表名，以及它们在数据库中是否真实存在。

---

## 9. 审批流工具

### 9.1 kingdee_query_pending_approvals

```json
{
  "tool": "kingdee_query_pending_approvals",
  "params": {
    "form_id": "",
    "status": "pending",
    "limit": 20
  }
}
```

`status` 取值：`pending`（待审批）、`approved`（已审核）、`rejected`（已驳回）、`all`

### 9.2 kingdee_workflow_approve

```json
{
  "tool": "kingdee_workflow_approve",
  "params": {
    "form_id": "ER_ExpenseReimburse",
    "bill_id": "200001",
    "action": "approve",
    "opinion": "同意报销"
  }
}
```

`action` 取值：`approve`（通过）、`reject`（驳回）

---

## 10. 常见陷阱与注意事项

### 10.1 HTTP/2 兼容性（已由 MCP Server 自动处理）

- httpx 0.28+ 默认使用 HTTP/2，但金蝶 WebAPI 不支持
- MCP Server 已强制使用 `http1=True`，Agent 无需关注

### 10.2 data 字段双重编码（已由 MCP Server 自动处理）

- Kingdee WebAPI 的 `data` 字段本身是 JSON 字符串：`{"formid":"...", "data":"{\"Model\":{...}}"}`
- MCP Server 已正确处理，Agent 调用 `kingdee_save_bill` 时直接传 `model` dict 即可

### 10.3 Submit/Audit/Unaudiot/Delete 的 Ids 格式（已由 MCP Server 自动处理）

- 这四个接口的 `Ids` 必须是**单个字符串**，不是数组
- 如 `{"Ids": "100012"}`，而不是 `{"Ids": ["100012"]}`
- MCP Server 会自动处理：若传入数组则取第一个元素

### 10.4 Save API 返回值格式兼容

不同 Kingdee 接口返回的 FID/FBillNo 格式不同：

```python
# 三种可能格式，AI 需要全部兼容：
result.get("FID")                       # 格式 1
result.get("Id")                        # 格式 2
result.get("SuccessEntitys", [{}])[0].get("Id")  # 格式 3
```

### 10.5 Demo 环境字段缺失

Demo 账套缺少供应链高级字段，使用替代方案：

| 需要用的字段 | Demo 替代方案 |
|------------|------------|
| `FLinkQty` | `FReceiveQty + FStockInQty` |
| `FTotalAmount` | `FAllAmount` 或 `FPOOrderEntry.FAllAmount` 求和 |
| `FCloseStatus` | `FDocumentStatus` 判断 |
| `FBusinessClose` | 无，需业务逻辑判断 |

### 10.6 分页与全量查询

- `limit` 最大为 100
- `start_row` 从 0 开始
- `has_more: true` 表示还有更多数据，需要翻页继续查

### 10.7 日期格式

- Query 的 `filter_string` 中日期用字符串：`FDate>='2026-01-01'`
- Save 的 `model` 中日期字段用 ISO 字符串：`"FDate": "2026-04-10"`

### 10.8 View 响应双层嵌套

```python
bill_data = result["Result"]["Result"]  # View 响应有两层嵌套
```

---

## 11. 完整调用流程示例

### 场景：新建一张采购订单 → 提交 → 审核 → 下推入库

**Step 1：查询供应商和物料信息**

```json
{
  "tool": "kingdee_query_partners",
  "params": { "partner_type": "BD_Supplier", "filter_string": "FNumber='S001'" }
}
```

```json
{
  "tool": "kingdee_query_materials",
  "params": { "filter_string": "FNumber='MAT001'" }
}
```

**Step 2：新建采购订单**

```json
{
  "tool": "kingdee_save_bill",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "model": {
      "FDate": "2026-04-10",
      "FSupplierId": { "FNumber": "S001" },
      "FPurchaseDeptId": { "FNumber": "D001" },
      "FPOOrderEntry": [
        {
          "FMaterialId": { "FNumber": "MAT001" },
          "FQty": 100,
          "FPrice": 50,
          "FTaxRate": 13
        }
      ]
    }
  }
}
```

假设返回 `FID: "100105"`, `FBillNo: "CGDD2026040105"`

**Step 3：提交（草稿→待审核）**

```json
{
  "tool": "kingdee_submit_bills",
  "params": { "form_id": "PUR_PurchaseOrder", "bill_ids": ["100105"] }
}
```

**Step 4：审核（待审核→已审核）**

```json
{
  "tool": "kingdee_audit_bills",
  "params": { "form_id": "PUR_PurchaseOrder", "bill_ids": ["100105"] }
}
```

**Step 5：查询执行进度，确认可下推数量**

```json
{
  "tool": "kingdee_query_purchase_order_progress",
  "params": { "filter_string": "FBillNo='CGDD2026040105'" }
}
```

假设 `FReceiveQty: 0, FStockInQty: 0`，则整单可下推

**Step 6：下推生成采购入库单**

```json
{
  "tool": "kingdee_push_bill",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "target_form_id": "STK_InStock",
    "source_bill_nos": ["CGDD2026040105"],
    "rule_id": "PUR_PurchaseOrder-STK_InStock"
  }
}
```

假设返回 `Ids: ["300015"]`, `Numbers: ["CGRKD2026040015"]`

**Step 7：提交+审核入库单**

```json
{
  "tool": "kingdee_submit_bills",
  "params": { "form_id": "STK_InStock", "bill_ids": ["300015"] }
}
```

```json
{
  "tool": "kingdee_audit_bills",
  "params": { "form_id": "STK_InStock", "bill_ids": ["300015"] }
}
```

**Step 8：验证采购订单执行进度已更新**

```json
{
  "tool": "kingdee_query_purchase_order_progress",
  "params": { "filter_string": "FBillNo='CGDD2026040105'" }
}
```

预期：`FStockInQty` 已更新为 100。

---

## 附录 A：FORM_CATALOG 表单目录摘要

| form_id | 中文名 | 别名 | 主要字段 |
|---------|--------|------|---------|
| `BD_Material` | 物料 | 物料/材料/商品/产品 | FNumber, FName, FSpecification |
| `BD_Supplier` | 供应商 | 供应商/厂家 | FNumber, FName |
| `BD_Customer` | 客户 | 客户/客户档案 | FNumber, FName |
| `BD_Department` | 部门 | 部门/组织 | FNumber, FName |
| `BD_Empinfo` | 员工 | 员工/人员/采购员 | FNumber, FName, FDeptId |
| `BD_Stock` | 仓库 | 仓库/库房 | FNumber, FName |
| `PUR_PurchaseOrder` | 采购订单 | 采购订单/PO | FID, FBillNo, FSupplierId, FTaxAmount |
| `PUR_ReceiveBill` | 收料通知单 | 收料通知/到货通知 | FID, FBillNo, FSupplierId |
| `PUR_Requisition` | 采购申请单 | 采购申请/请购单 | FID, FBillNo, FApplicantId |
| `SAL_SaleOrder` | 销售订单 | 销售订单/SO | FID, FBillNo, FCustId, FTotalAmount |
| `SAL_OUTSTOCK` | 销售出库单 | 销售出库/出货单 | FID, FBillNo, FCustId |
| `STK_InStock` | 采购入库单 | 采购入库/入库单 | FID, FBillNo, FSupplierId, FInQty |
| `STK_Inventory` | 即时库存 | 库存/即时库存 | FMaterialId, FStockId, FBaseQty |
| `ER_ExpenseReimburse` | 费用报销单 | 费用报销/报销单 | FID, FBillNo, FApplicantId, FTotalReimAmount |
| `PRD_MO` | 生产订单 | 生产订单/MO/工单 | FID, FBillNo, FMaterialId, FQty |

## 附录 B：错误处理

| HTTP 状态码 | 含义 | 建议 |
|------------|------|------|
| 401 | 认证失败 | 检查 KINGDEE_APP_ID / APP_SEC 是否正确 |
| 403 | 权限不足 | 检查集成用户是否有该单据的操作权限 |
| 404 | 接口不存在 | 检查 KINGDEE_SERVER_URL 是否正确（结尾必须是 `/k3cloud/`） |
| 502 | Bad Gateway | 通常是 HTTP/2 问题，已由 MCP Server 处理；或参数格式错误 |
| 超时 | 请求超时 | 检查服务器连通性或网络延迟 |

---

*本文档由 Claude Code 自动生成，基于 `src/kingdee_mcp/server.py` 源码。*
*如工具行为与文档不符，请以源码注释和工具 description 为准。*
