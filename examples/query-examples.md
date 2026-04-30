# 查询参数示例（filter_string / field_keys）

本文件提供 filter_string 和 field_keys 的常用示例，按业务场景分组。

---

## 采购订单（PUR_PurchaseOrder）

### filter_string 示例

| 场景 | filter_string |
|------|----------------|
| 已审核单据 | `FDocumentStatus='C'` |
| 草稿单据 | `FDocumentStatus='A'` |
| 指定供应商 | `FSupplierId.FNumber='S001'` |
| 指定物料 | `FMaterialId.FNumber='MAT001'` |
| 指定单号 | `FBillNo='PO2026040001'` |
| 本月单据 | `FDate>='2026-04-01' and FDate<='2026-04-30'` |
| 金额大于 | `FTotalAmount>10000` |
| 未完成入库 | `FReceiveQty+FPStockInQty<FQty` |
| 指定采购员 | `FPurchaserId.FNumber='EMP001'` |
| 指定部门 | `FPurchaseDeptId.FNumber='DEPT001'` |
| 模糊搜索供应商 | `FSupplierId.FName like '%深圳%'` |
| 模糊搜索物料 | `FMaterialId.FName like '%钢材%'` |
| 多条件组合 | `FDocumentStatus='C' and FSupplierId.FNumber='S001' and FDate>='2026-04-01'` |

### field_keys 示例

```
FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FNumber,FSupplierId.FName,FPurchaserId.FName,FTotalAmount,FMaterialId.FNumber,FMaterialId.FName,FQty,FReceiveQty,FStockInQty
```

---

## 销售订单（SAL_SaleOrder）

### filter_string 示例

| 场景 | filter_string |
|------|----------------|
| 已审核单据 | `FDocumentStatus='C'` |
| 指定客户 | `FCustId.FNumber='C001'` |
| 指定物料 | `FMaterialId.FNumber='MAT001'` |
| 指定单号 | `FBillNo='SO2026040001'` |
| 本月单据 | `FDate>='2026-04-01' and FDate<='2026-04-30'` |
| 未完成出库 | `FStockOutQty<FQty` |
| 指定销售员 | `FSalesManId.FNumber='EMP001'` |
| 指定销售组织 | `FSalesOrgId.FNumber='ORG001'` |
| 模糊搜索客户 | `FCustId.FName like '%北京%'` |

### field_keys 示例

```
FID,FBillNo,FDate,FDocumentStatus,FCustId.FNumber,FCustId.FName,FSalesManId.FName,FTotalAmount,FMaterialId.FNumber,FMaterialId.FName,FQty,FStockOutQty,FDeliQty
```

---

## 生产订单（PRD_MO）

### filter_string 示例

| 场景 | filter_string |
|------|----------------|
| 已审核单据 | `FDocumentStatus='C'` |
| 指定物料 | `FMaterialId.FNumber='MAT001'` |
| 指定单号 | `FBillNo='MO2026040001'` |
| 本月单据 | `FDate>='2026-04-01' and FDate<='2026-04-30'` |
| 未完成入库 | `FQty>FStockInQty` |
| 未完成领料 | `FQty>FPickMtrlQty` |
| 指定车间 | `FWorkShopId.FNumber='WS001'` |
| 计划开工日期 | `FPlanStartDate>='2026-05-01'` |
| 计划完工日期 | `FPlanFinishDate<='2026-05-31'` |
| 生产状态 | `FStatus=2` |

### field_keys 示例

```
FID,FBillNo,FDate,FDocumentStatus,FMaterialId.FNumber,FMaterialId.FName,FWorkShopId.FName,FQty,FPlanStartDate,FPlanFinishDate,FStockInQty,FPickMtrlQty,FStatus
```

---

## 即时库存（STK_Inventory）

### filter_string 示例

| 场景 | filter_string |
|------|----------------|
| 指定物料 | `FMaterialId.FNumber='MAT001'` |
| 指定仓库 | `FStockId.FNumber='STOCK001'` |
| 模糊搜索物料 | `FMaterialId.FName like '%钢材%'` |
| 模糊搜索仓库 | `FStockId.FName like '%原料%'` |
| 有库存数量 | `FBaseQty>0` |
| 组合条件 | `FMaterialId.FNumber like 'MAT%' and FStockId.FNumber='STOCK001'` |

### field_keys 示例

```
FMaterialId.FNumber,FMaterialId.FName,FStockId.FNumber,FStockId.FName,FStockLocId.FName,FBaseQty,FSecQty,FUnitId.FName,FKeeperId.FName
```

---

## 物料（BD_Material）

### filter_string 示例

| 场景 | filter_string |
|------|----------------|
| 已审核物料 | `FDocumentStatus='C'` |
| 指定编码 | `FNumber='MAT001'` |
| 模糊搜索名称 | `FName like '%钢材%'` |
| 模糊搜索规格 | `FSpecification like '%10mm%'` |
| 指定物料组 | `FMaterialGroup.FNumber='MG001'` |
| 组合搜索 | `FName like '%A%' and FMaterialGroup.FNumber='MG001'` |

### field_keys 示例

```
FMaterialId,FNumber,FName,FSpecification,FUnitID.FName,FMaterialGroup.FName,FDocumentStatus
```

---

## 客户/供应商（BD_Customer / BD_Supplier）

### filter_string 示例（客户）

| 场景 | filter_string |
|------|----------------|
| 已审核客户 | `FDocumentStatus='C'` |
| 指定编码 | `FNumber='C001'` |
| 模糊搜索名称 | `FName like '%北京%'` |
| 模糊搜索简称 | `FShortName like '%华%'` |

### field_keys 示例（客户）

```
FCustomerId,FNumber,FName,FShortName,FContact,FPhone,FDocumentStatus
```

### filter_string 示例（供应商）

| 场景 | filter_string |
|------|----------------|
| 已审核供应商 | `FDocumentStatus='C'` |
| 指定编码 | `FNumber='S001'` |
| 模糊搜索名称 | `FName like '%华%'` |

### field_keys 示例（供应商）

```
FSupplierId,FNumber,FName,FShortName,FContact,FPhone,FDocumentStatus
```

---

## 成本查询

### 物料成本库（BD_MaterialCost）

| 场景 | filter_string |
|------|----------------|
| 指定物料 | `FMaterialId.FNumber='MAT001'` |
| 模糊搜索物料 | `FMaterialId.FName like '%钢材%'` |
| 有标准成本 | `FStdCost>0` |
| 有最新成本 | `FLatestCost>0` |

```
FMaterialId.FNumber,FMaterialId.FName,FUnitId.FName,FStdCost,FLatestCost,FAvgCost
```

### 成本调整单（STK_CostAdjust）

| 场景 | filter_string |
|------|----------------|
| 已审核单据 | `FDocumentStatus='C'` |
| 调价类型 | `FAdjustType=1` |
| 调差类型 | `FAdjustType=2` |
| 指定成本组织 | `FCostOrgId.FNumber='ORG001'` |
| 本月单据 | `FDate>='2026-04-01' and FDate<='2026-04-30'` |

```
FID,FBillNo,FDate,FDocumentStatus,FCostOrgId.FNumber,FCostOrgId.FName,FAdjustType,FAdjustAmount
```

---

## 通用查询（kingdee_query_bills）

当没有专用查询工具时，使用通用查询：

```json
{
  "tool": "kingdee_query_bills",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "filter_string": "FDocumentStatus='C' and FDate>='2026-04-01'",
    "field_keys": "FID,FBillNo,FDate,FSupplierId.FName,FTotalAmount",
    "order_string": "FDate DESC",
    "start_row": 0,
    "limit": 20
  }
}
```

### 常用 form_id 速查

| 业务 | form_id |
|------|---------|
| 采购订单 | `PUR_PurchaseOrder` |
| 销售订单 | `SAL_SaleOrder` |
| 生产订单 | `PRD_MO` |
| 生产领料单 | `PRD_PickMtrl` |
| 产品入库单 | `PRD_Instock` |
| 采购入库单 | `STK_InStock` |
| 销售出库单 | `SAL_OUTSTOCK` |
| 即时库存 | `STK_Inventory` |
| 物料 | `BD_Material` |
| 客户 | `BD_Customer` |
| 供应商 | `BD_Supplier` |
| 物料成本 | `BD_MaterialCost` |
| 成本调整单 | `STK_CostAdjust` |

---

## SQL LIKE 特殊字符转义

注意：`filter_string` 使用 Kingdee 的 SQL LIKE 语法。

| 字符 | 转义方式 |
|------|----------|
| `%` | `[%]` |
| `_` | `[_]` |
| `[` | `[[]` |
| `'` | `''`（两个单引号） |

示例：搜索包含 `100%` 的物料名称：
```
FName like '%100[%]%'
```

---

## 日期格式

Kingdee API 使用以下日期格式：

| 格式 | 示例 |
|------|------|
| 日期 | `2026-04-30` |
| 日期时间 | `2026-04-30 12:00:00` |
| 月份 | `2026-04` |

---

## 操作符速查

| 操作符 | 说明 | 示例 |
|--------|------|------|
| `=` | 等于 | `FDocumentStatus='C'` |
| `<>` | 不等于 | `FStatus<>0` |
| `>` | 大于 | `FTotalAmount>1000` |
| `>=` | 大于等于 | `FQty>=100` |
| `<` | 小于 | `FGapQty<0` |
| `<=` | 小于等于 | `FStockInQty<=FQty` |
| `like` | 模糊匹配 | `FName like '%钢材%'` |
| `in` | 在列表中 | `FStatus in (1,2,3)` |
| `and` | 逻辑与 | `A and B` |
| `or` | 逻辑或 | `A or B` |
| `not` | 逻辑非 | `not (A and B)` |

---

## 分页参数

```json
{
  "start_row": 0,    // 从第0行开始（第一页）
  "limit": 20        // 每页20条
}
```

分页查询下一页：
```json
{
  "start_row": 20,   // 从第20行开始（第二页）
  "limit": 20
}
```

检查是否有更多数据：查看返回结果中的 `has_more` 字段（`true`=还有数据）。
