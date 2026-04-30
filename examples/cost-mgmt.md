# 成本管理模块 API 文档

金蝶 MCP 成本管理模块涵盖存货核算、产品成本核算、标准成本分析等功能。

---

## 1. 存货核算

### kingdee_query_material_cost

查询物料成本库（`BD_MaterialCost`）。

物料成本库存储物料的标准成本、最新成本、平均成本等价格信息，是存货核算的基础资料。

**功能说明**：查询物料的当前成本价格数据

**filter_string 示例**：
```
FMaterialId.FNumber='MAT001'
FMaterialId.FName like '%钢材%'
FStdCost>0
FStdCost>0 and FAvgCost>0
```

**推荐 field_keys**：
```
FMaterialId.FNumber,FMaterialId.FName,FUnitId.FName,FStdCost,FLatestCost,FAvgCost
```

---

### kingdee_query_material_target_cost

查询物料目标成本单（`BD_MatTargetCost`）。

物料目标成本单用于设置物料的目标成本，用于成本控制和预算分析。

**功能说明**：查询物料目标成本设置

**filter_string 示例**：
```
FDocumentStatus='C'
FMaterialId.FNumber='MAT001'
FDate>='2024-01-01' and FDate<='2024-12-31'
FDocumentStatus='C' and FMaterialId.FName like '%钢材%'
```

**推荐 field_keys**：
```
FID,FBillNo,FDate,FDocumentStatus,FMaterialId.FNumber,FMaterialId.FName,FUnitId.FName,FTargetCost
```

---

### kingdee_query_cost_adjustments

查询成本调整单（`STK_CostAdjust`）。

成本调整单用于对存货成本进行调整，处理成本核算中的差异调整。

**功能说明**：查询成本调整记录

**filter_string 示例**：
```
FDocumentStatus='C'
FAdjustType=1
FAdjustType=2
FCostOrgId.FNumber='ORG001'
FDate>='2024-01-01' and FDate<='2024-12-31'
FCostOrgId.FNumber='ORG001' and FDocumentStatus='C'
```

**推荐 field_keys**：
```
FID,FBillNo,FDate,FDocumentStatus,FCostOrgId.FNumber,FCostOrgId.FName,FAdjustType,FAdjustAmount
```

**字段说明**：
| 字段 | 含义 |
|------|------|
| FAdjustType | 调整类型（1=调价, 2=调差） |
| FAdjustAmount | 调整金额 |

---

### kingdee_save_cost_adjustment

新建或修改成本调整单（`STK_CostAdjust`）。

成本调整单用于调整存货成本，处理成本核算差异。

**功能说明**：新建或修改成本调整单

**model 示例**：
```json
{
  "FDate": "2024-01-15",
  "FCostOrgId": {"FNumber": "ORG001"},
  "FAdjustType": 1,
  "FEntity": [
    {
      "FMaterialId": {"FNumber": "MAT001"},
      "FUnitId": {"FNumber": "PCS"},
      "FCurrentCost": 10.5,
      "FAdjustCost": 11.0,
      "FAdjustQty": 100,
      "FAdjustAmount": 50.0
    }
  ]
}
```

**注意事项**：成本调整单审核后生效，会影响当期存货成本

---

## 2. 产品成本核算

### kingdee_query_cost_items

查询成本项目基础资料（`CB_CostItem`）。

成本项目是归集和分配费用的对象。

**功能说明**：查询成本项目基础资料

**filter_string 示例**：
```
FCostItemType=1
FIsActive='1'
FName like '%制造%'
```

**推荐 field_keys**：
```
FNumber,FName,FCostItemType,FIsActive
```

**字段说明**：
| 字段 | 含义 |
|------|------|
| FNumber | 编码 |
| FName | 名称 |
| FCostItemType | 类型 |
| FIsActive | 是否禁用 |

---

### kingdee_query_cost_centers

查询成本中心基础资料（`CB_CostCenter`）。

成本中心是成本核算的责任单元。

**功能说明**：查询成本中心基础资料

**filter_string 示例**：
```
FIsActive='1'
FDeptId.FNumber='DEPT001'
FName like '%生产%'
```

**推荐 field_keys**：
```
FNumber,FName,FDeptId.FName,FIsActive
```

**字段说明**：
| 字段 | 含义 |
|------|------|
| FNumber | 编码 |
| FName | 名称 |
| FDeptId.FName | 关联部门 |
| FIsActive | 是否禁用 |

---

### kingdee_query_product_group

查询产品组基础资料（`CB_ProductGroup`）。

**功能说明**：查询产品组基础资料

**filter_string 示例**：
```
FIsActive='1'
FName like '%A系列%'
```

**推荐 field_keys**：
```
FNumber,FName,FIsActive
```

---

### kingdee_query_expense_allocation_std

查询费用分配标准基础资料（`CB_ExpenseAllocStd`）。

**功能说明**：查询费用分配标准

**filter_string 示例**：
```
FIsActive='1'
FAllocRule.FName like '%产量%'
```

**推荐 field_keys**：
```
FNumber,FName,FAllocRule.FName,FIsActive
```

---

### kingdee_query_work_activities

查询作业活动基础资料（`CB_WorkActivity`）。

**功能说明**：查询作业活动

**filter_string 示例**：
```
FIsActive='1'
FCostItemId.FName like '%加工%'
```

**推荐 field_keys**：
```
FNumber,FName,FCostItemId.FName,FIsActive
```

---

### kingdee_query_byproduct_cost

查询副产品定额成本基础资料（`CB_ByProductCost`）。

**功能说明**：查询副产品定额成本

**filter_string 示例**：
```
FMaterialId.FNumber like 'BY%'
FMaterialId.FName like '%废料%'
```

**推荐 field_keys**：
```
FMaterialId.FNumber,FMaterialId.FName,FCostPrice,FUnitId.FName
```

---

## 3. 标准成本分析

### 通用查询模式

成本分析数据通常存储在报表类单据中，可通过 `kingdee_query_bills` 工具查询。

**常用 form_id**：
| form_id | 说明 |
|---------|------|
| CB_CostReport | 成本报表 |
| CB_StandardCost | 标准成本 |
| CB_CostVariance | 成本差异 |

**filter_string 示例**：
```
FPeriod='2024-01'
FMaterialId.FNumber='MAT001'
FDocumentStatus='C'
```

---

## 4. 成本报表

### kingdee_query_bills（通用报表查询）

通过通用单据查询工具查询成本相关的报表数据。

**功能说明**：查询成本相关报表

**form_id 示例**：
```
CB_CostReport
CB_ProductCost
```

**filter_string 示例**：
```
FPeriod='2024-01'
FDocumentStatus='C'
FMaterialId.FNumber='MAT001'
```

---

## 快速查询示例

### 查询某物料的当前成本
```json
{
  "tool": "kingdee_query_material_cost",
  "params": {
    "filter_string": "FMaterialId.FNumber='MAT001'",
    "field_keys": "FMaterialId.FNumber,FMaterialId.FName,FStdCost,FLatestCost,FAvgCost",
    "start_row": 0,
    "limit": 10
  }
}
```

### 查询成本调整单列表
```json
{
  "tool": "kingdee_query_cost_adjustments",
  "params": {
    "filter_string": "FDocumentStatus='C'",
    "field_keys": "FID,FBillNo,FDate,FCostOrgId.FName,FAdjustType,FAdjustAmount",
    "start_row": 0,
    "limit": 20
  }
}
```

### 查询成本中心基础资料
```json
{
  "tool": "kingdee_query_cost_centers",
  "params": {
    "filter_string": "FIsActive='1'",
    "field_keys": "FNumber,FName,FDeptId.FName,FIsActive",
    "start_row": 0,
    "limit": 50
  }
}
```

### 查询成本项目基础资料
```json
{
  "tool": "kingdee_query_cost_items",
  "params": {
    "filter_string": "FIsActive='1'",
    "field_keys": "FNumber,FName,FCostItemType,FIsActive",
    "start_row": 0,
    "limit": 50
  }
}
```

---

## 注意事项

1. **成本调整单审核生效**：成本调整单需要提交+审核后才能影响存货成本
2. **期间限制**：成本数据通常与会计期间关联，查询时注意指定期间
3. **基础资料优先**：查询成本前，建议先确认成本项目、成本中心等基础资料已正确设置
4. **权限要求**：成本相关查询可能需要成本模块权限

---

## 5. 成本分析报表

### kingdee_query_instant_cost_compare（即时成本对比）

查询物料的即时成本与账面成本对比。

**功能说明**：实时对比分析物料的即时成本与账面成本差异

**filter_string 示例**：
```
FPeriod='2026-04'
FMaterialId.FNumber='MAT001'
FCostOrgId.FNumber='ORG001'
```

**推荐 field_keys**：
```
FID,FPeriod,FMaterialId.FNumber,FMaterialId.FName,FInstantCost,FAvgCost,FStdCost,FCostDiff
```

### kingdee_query_cost_trend（成本趋势分析）

分析物料成本价格的历史变化趋势。

**功能说明**：查询物料成本的历史变化趋势

**filter_string 示例**：
```
FMaterialId.FNumber='MAT001'
FPeriod>='2026-01' and FPeriod<='2026-04'
FChangeRate>0
```

**推荐 field_keys**：
```
FID,FMaterialId.FNumber,FMaterialId.FName,FPeriod,FStartCost,FCurrentCost,FChangeRate
```

### kingdee_query_bill_cost_compare（单据成本对比）

对比分析核算单据中不同来源的成本差异。

**功能说明**：分析入库单据的实际成本与标准成本差异

**filter_string 示例**：
```
FDate>='2026-04-01' and FDate<='2026-04-30'
FBillType='STK_InStock'
FCostDiff<>0
```

**推荐 field_keys**：
```
FID,FBillNo,FMaterialId.FName,FBillType,FSourceCost,FActualCost,FCostDiff
```

---

## 6. 产品成本核算

### kingdee_query_cost_calculation（成本计算单查询）

查询产品成本核算的计算过程和结果。

**功能说明**：查询成本计算单，记录成本计算过程

**filter_string 示例**：
```
FPeriod='2026-04'
FDocumentStatus='C'
FCostOrgId.FNumber='ORG001'
```

**推荐 field_keys**：
```
FID,FBillNo,FPeriod,FDate,FDocumentStatus,FCostOrgId.FName,FTotalCost,FMaterialCost,FLaborCost,FExpenseCost
```

### kingdee_query_finished_product_cost（完工产品成本查询）

查询完工入库产品的成本数据。

**功能说明**：查询生产完工入库产品的成本

**filter_string 示例**：
```
FPeriod='2026-04'
FMaterialId.FNumber like 'FIN%'
FDocumentStatus='C'
```

**推荐 field_keys**：
```
FID,FPeriod,FMaterialId.FNumber,FMaterialId.FName,FWorkShopId.FName,FInQty,FCostAmount,FUnitCost
```

### kingdee_query_material_cost_usage（材料耗用成本查询）

查询生产过程中材料的耗用成本。

**功能说明**：统计各生产订单/工序的材料消耗成本

**filter_string 示例**：
```
FPeriod='2026-04'
FWorkShopId.FNumber='WS001'
FCostAmount>0
```

**推荐 field_keys**：
```
FID,FPeriod,FMaterialId.FNumber,FMaterialId.FName,FWorkShopId.FName,FQty,FCostAmount
```

### kingdee_query_sales_order_cost_tracking（销售订单成本跟踪）

跟踪销售订单从接单到出库的成本变化。

**功能说明**：分析销售订单的毛利和成本构成

**filter_string 示例**：
```
FSOBillNo='SO2026040001'
FCustomerId.FNumber='C001'
```

**推荐 field_keys**：
```
FID,FSOBillNo,FCustomerId.FName,FMaterialId.FName,FOrderQty,FCostPrice,FCostAmount,FGrossProfit
```

---

## 7. 成本还原与差异分析

### kingdee_query_cost_restore_compare（成本还原对比）

查询成本还原后的数据对比。

**filter_string 示例**：
```
FPeriod='2026-04'
FMaterialId.FNumber='MAT001'
```

**推荐 field_keys**：
```
FID,FPeriod,FMaterialId.FNumber,FMaterialId.FName,FStdCost,FActualCost,FRestoreAmount
```

### kingdee_query_cost_variance_analysis（成本差异分析）

分析实际成本与标准成本的差异。

**filter_string 示例**：
```
FPeriod='2026-04'
FCostVarianceType='MAT'   -- 材料差异
FCostVarianceType='LAB'   -- 人工差异
FCostVarianceType='EXP'   -- 费用差异
```

**推荐 field_keys**：
```
FID,FPeriod,FMaterialId.FNumber,FMaterialId.FName,FCostVarianceType,FStdAmount,FActualAmount,FVarianceAmount,FVarianceRate
```

---

## 8. BOM 与成本版本

### kingdee_query_cost_bom（成本BOM查询）

查询物料的成本BOM结构。

**filter_string 示例**：
```
FMaterialId.FNumber='MAT001'
FBOMLevel=1
FIsEffective='1'
```

**推荐 field_keys**：
```
FID,FMaterialId.FNumber,FMaterialId.FName,FMaterialId.FParentId.FName,FChildMaterialId.FNumber,FChildMaterialId.FName,FQty,FUnitCost,FAmount
```

### kingdee_query_cost_versions（成本版本查询）

查询成本计算的版本记录。

**filter_string 示例**：
```
FPeriod='2026-04'
FCostVersionType='STD'   -- 标准成本版本
FCostVersionType='ACT'   -- 实际成本版本
FIsLatest='1'
```

**推荐 field_keys**：
```
FID,FPeriod,FCostVersionType,FVersionNo,FDocumentStatus,FCreateDate,FApproveDate
```

---

## 9. 车间成本

### kingdee_query_workshop_cost（车间成本查询）

查询各车间的成本发生数据。

**filter_string 示例**：
```
FPeriod='2026-04'
FWorkShopId.FNumber='WS001'
FDocumentStatus='C'
```

**推荐 field_keys**：
```
FID,FPeriod,FWorkShopId.FNumber,FWorkShopId.FName,FCostItemId.FName,FAmount,FQty,FUnitCost
```

---

## 10. 在制品（WIP）成本

### kingdee_query_wip_initial_cost（在制品期初成本）

查询在制品的期初成本数据。

**filter_string 示例**：
```
FPeriod='2026-04'
FWorkShopId.FNumber='WS001'
FDocumentStatus='C'
```

**推荐 field_keys**：
```
FID,FPeriod,FMaterialId.FNumber,FMaterialId.FName,FWorkShopId.FName,FWorkOrderNo,FInitialQty,FInitialCost
```

### kingdee_query_wip_count（在制品盘点）

查询在制品盘点数据。

**filter_string 示例**：
```
FDate>='2026-04-01' and FDate<='2026-04-30'
FWorkShopId.FNumber='WS001'
```

**推荐 field_keys**：
```
FID,FDate,FWorkShopId.FNumber,FWorkShopId.FName,FMaterialId.FNumber,FMaterialId.FName,FBookQty,FActualQty,FVarianceQty
```

---

## 11. 完工与作业

### kingdee_query_finished_quantity（完工产量查询）

查询生产完工产量数据。

**filter_string 示例**：
```
FPeriod='2026-04'
FWorkShopId.FNumber='WS001'
FDocumentStatus='C'
```

**推荐 field_keys**：
```
FID,FPeriod,FWorkShopId.FName,FMaterialId.FNumber,FMaterialId.FName,FFinishedQty,FQualifiedQty,FRejectQty
```

### kingdee_query_equivalent_factor（等量因子维护）

查询或维护产品/副产品的等量因子。

**filter_string 示例**：
```
FProductId.FNumber='MAT001'
FIsActive='1'
```

**推荐 field_keys**：
```
FID,FProductId.FNumber,FProductId.FName,FByProductId.FNumber,FByProductId.FName,FEquivalentQty,FUnitId.FName
```

### kingdee_query_operation_quantity（作业数量查询）

查询各作业中心的作业数量数据。

**filter_string 示例**：
```
FPeriod='2026-04'
FCostCenterId.FNumber='CC001'
```

**推荐 field_keys**：
```
FID,FPeriod,FCostCenterId.FName,FWorkActivityId.FName,FQuantity,FUnitId.FName,FAmount
```

### kingdee_query_shared_material_scope（共耗材料范围）

查询各产品共耗材料的归属范围。

**filter_string 示例**：
```
FProductId.FNumber='FIN001'
FIsActive='1'
```

**推荐 field_keys**：
```
FID,FProductId.FNumber,FProductId.FName,FMaterialId.FNumber,FMaterialId.FName,FAllocRatio,FAllocMethod
```

---

## 快速查询示例汇总

### 查询本期完工产品的成本汇总
```json
{
  "tool": "kingdee_query_finished_product_cost",
  "params": {
    "filter_string": "FPeriod='2026-04' and FDocumentStatus='C'",
    "field_keys": "FID,FMaterialId.FNumber,FMaterialId.FName,FInQty,FCostAmount,FUnitCost",
    "start_row": 0,
    "limit": 50
  }
}
```

### 分析成本差异
```json
{
  "tool": "kingdee_query_cost_variance_analysis",
  "params": {
    "filter_string": "FPeriod='2026-04'",
    "field_keys": "FID,FMaterialId.FNumber,FMaterialId.FName,FCostVarianceType,FVarianceAmount,FVarianceRate",
    "start_row": 0,
    "limit": 50
  }
}
```

### 查询车间成本明细
```json
{
  "tool": "kingdee_query_workshop_cost",
  "params": {
    "filter_string": "FPeriod='2026-04' and FDocumentStatus='C'",
    "field_keys": "FID,FWorkShopId.FName,FCostItemId.FName,FAmount,FQty",
    "start_row": 0,
    "limit": 50
  }
}
```

### 查询在制品期初成本
```json
{
  "tool": "kingdee_query_wip_initial_cost",
  "params": {
    "filter_string": "FPeriod='2026-04' and FDocumentStatus='C'",
    "field_keys": "FID,FMaterialId.FNumber,FMaterialId.FName,FWorkOrderNo,FInitialQty,FInitialCost",
    "start_row": 0,
    "limit": 50
  }
}
```

### 查询完工产量统计
```json
{
  "tool": "kingdee_query_finished_quantity",
  "params": {
    "filter_string": "FPeriod='2026-04' and FDocumentStatus='C'",
    "field_keys": "FID,FMaterialId.FNumber,FMaterialId.FName,FFinishedQty,FQualifiedQty,FRejectQty",
    "start_row": 0,
    "limit": 50
  }
}
```

### 查询即时成本对比
```json
{
  "tool": "kingdee_query_instant_cost_compare",
  "params": {
    "filter_string": "FPeriod='2026-04'",
    "field_keys": "FID,FMaterialId.FNumber,FMaterialId.FName,FInstantCost,FAvgCost,FStdCost,FCostDiff",
    "start_row": 0,
    "limit": 50
  }
}
```

### 查询成本趋势
```json
{
  "tool": "kingdee_query_cost_trend",
  "params": {
    "filter_string": "FMaterialId.FNumber='MAT001' and FPeriod>='2026-01'",
    "field_keys": "FID,FMaterialId.FNumber,FMaterialId.FName,FPeriod,FCurrentCost,FChangeRate",
    "start_row": 0,
    "limit": 12
  }
}
```

---

## 完整成本工具索引

| 工具 | 说明 | 表单 |
|------|------|------|
| **基础资料** |||
| `kingdee_query_cost_items` | 成本项目 | CB_CostItem |
| `kingdee_query_cost_centers` | 成本中心 | CB_CostCenter |
| `kingdee_query_product_group` | 产品组 | CB_ProductGroup |
| `kingdee_query_expense_allocation_std` | 费用分配标准 | CB_ExpenseAllocStd |
| `kingdee_query_work_activities` | 作业活动 | CB_WorkActivity |
| `kingdee_query_byproduct_cost` | 副产品定额成本 | CB_ByProductCost |
| **存货核算** |||
| `kingdee_query_material_cost` | 物料成本库 | BD_MaterialCost |
| `kingdee_query_material_target_cost` | 物料目标成本 | BD_MatTargetCost |
| `kingdee_query_cost_adjustments` | 成本调整单 | STK_CostAdjust |
| `kingdee_save_cost_adjustment` | 新建成本调整单 | STK_CostAdjust |
| **成本分析** |||
| `kingdee_query_instant_cost_compare` | 即时成本对比 | STK_InstantCostCompare |
| `kingdee_query_cost_trend` | 成本趋势分析 | STK_CostTrend |
| `kingdee_query_bill_cost_compare` | 单据成本对比 | STK_CostCompare |
| `kingdee_query_period_cost_compare` | 期间成本对比 | - |
| `kingdee_query_cost_restore_compare` | 成本还原对比 | - |
| **产品成本** |||
| `kingdee_query_cost_calculation` | 成本计算单 | PC_CostBill |
| `kingdee_query_finished_product_cost` | 完工产品成本 | - |
| `kingdee_query_material_cost_usage` | 材料耗用成本 | PC_MaterialCostQuery |
| `kingdee_query_sales_order_cost_tracking` | 销售订单成本跟踪 | SAL_CostTrack |
| `kingdee_query_product_standard_cost` | 产品标准成本 | - |
| **差异与版本** |||
| `kingdee_query_cost_variance_analysis` | 成本差异分析 | - |
| `kingdee_query_cost_versions` | 成本版本 | - |
| `kingdee_query_cost_bom` | 成本BOM | - |
| **车间与在制品** |||
| `kingdee_query_workshop_cost` | 车间成本 | - |
| `kingdee_query_wip_initial_cost` | 在制品期初成本 | - |
| `kingdee_query_wip_count` | 在制品盘点 | - |
| **完工与作业** |||
| `kingdee_query_finished_quantity` | 完工产量 | - |
| `kingdee_query_equivalent_factor` | 等量因子 | - |
| `kingdee_query_operation_quantity` | 作业数量 | - |
| `kingdee_query_shared_material_scope` | 共耗材料范围 | - |
| **方案与调整** |||
| `kingdee_query_cost_item_scheme` | 成本项目方案 | - |
| `kingdee_query_operation_scheme` | 作业方案 | - |
| `kingdee_query_expense_import_scheme` | 费用引入方案 | - |
| `kingdee_save_cost_scope` | 成本范围保存 | - |
| `kingdee_save_period_end_adjust` | 期末成本调整 | - |
| `kingdee_save_period_start_adjust` | 期初成本调整 | - |