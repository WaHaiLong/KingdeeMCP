# 生产管理工具使用示例

## 场景说明

生产管理模块支持生产订单、生产领料单、产品入库单的全流程操作。

## 工具列表

| 工具 | 说明 | 表单 |
|------|------|------|
| kingdee_query_production_orders | 查询生产订单 | PRD_MO |
| kingdee_view_production_order | 查看生产订单详情 | PRD_MO |
| kingdee_save_production_order | 新建/修改生产订单 | PRD_MO |
| kingdee_submit_production_orders | 提交生产订单 | PRD_MO |
| kingdee_audit_production_orders | 审核生产订单 | PRD_MO |
| kingdee_push_production_pick | 生产订单下推领料单 | PRD_MO → PRD_PickMtrl |
| kingdee_push_production_stock_in | 下推开入库单 | PRD_PickMtrl/PRD_MO → PRD_Instock |
| kingdee_query_production_pick_materials | 查询生产领料单 | PRD_PickMtrl |
| kingdee_query_production_stock_in | 查询产品入库单 | PRD_Instock |
| kingdee_query_production_reports | 查询生产汇报单 | PRD_Report |
| kingdee_query_mrp_results | 查询MRP运算结果 | MRP_* |

## 生产流程

```
生产订单(PRD_MO) → 生产领料单(PRD_PickMtrl) → 产品入库单(PRD_Instock)
     ↓                    ↓                         ↓
   Save → Submit → Audit   Push → Submit → Audit     Push → Submit → Audit
```

---

## 1. 查询生产订单

### 用户提问

```
帮我查询已审核的生产订单，按日期倒序。
```

### AI 调用

```json
{
  "tool": "kingdee_query_production_orders",
  "params": {
    "filter_string": "FDocumentStatus='C'",
    "field_keys": "FID,FBillNo,FDate,FDocumentStatus,FWorkShopId.FName,FMaterialId.FNumber,FMaterialId.FName,FQty,FPlanStartDate,FPlanFinishDate",
    "order_string": "FDate DESC",
    "limit": 20
  }
}
```

### 返回结果

```json
{
  "count": 5,
  "has_more": false,
  "data": [
    {
      "FID": "100012",
      "FBillNo": "MO2026040001",
      "FDate": "2026-04-15",
      "FDocumentStatus": "C",
      "FWorkShopId.FName": "组装车间",
      "FMaterialId.FNumber": "MAT001",
      "FMaterialId.FName": "产品A",
      "FQty": 100,
      "FPlanStartDate": "2026-04-20",
      "FPlanFinishDate": "2026-04-25"
    }
  ]
}
```

---

## 2. 查看生产订单详情

### 用户提问

```
帮我查看生产订单 MO2026040001 的详细信息。
```

### AI 调用

首先查询生产订单获取 FID：

```json
{
  "tool": "kingdee_query_production_orders",
  "params": {
    "filter_string": "FBillNo='MO2026040001'",
    "field_keys": "FID"
  }
}
```

假设返回 FID 为 "100012"，然后查看详情：

```json
{
  "tool": "kingdee_view_production_order",
  "params": {
    "bill_id": "100012"
  }
}
```

### 返回结果

```json
{
  "Result": {
    "FBillNo": "MO2026040001",
    "FDate": "2026-04-15",
    "FDocumentStatus": "C",
    "FMaterialId": {"FNumber": "MAT001", "FName": "产品A"},
    "FQty": 100,
    "FPlanStartDate": "2026-04-20",
    "FPlanFinishDate": "2026-04-25",
    "FStockInQty": 0,
    "FPickMtrlQty": 0,
    "PRD_MOEntry": [
      {"FMaterialId": {"FNumber": "MAT002"}, "FQty": 50, "FStockInQty": 0}
    ]
  }
}
```

---

## 3. 新建生产订单

### 用户提问

```
帮我新建一张生产订单：
- 物料：MAT001（产品A）
- 数量：100
- 计划开工日期：2026-05-01
- 计划完工日期：2026-05-10
- 车间：WS001（组装车间）
```

### AI 调用

```json
{
  "tool": "kingdee_save_production_order",
  "params": {
    "model": {
      "FDate": "2026-04-30",
      "FWorkShopId": {"FNumber": "WS001"},
      "FMaterialId": {"FNumber": "MAT001"},
      "FQty": 100,
      "FPlanStartDate": "2026-05-01",
      "FPlanFinishDate": "2026-05-10",
      "FBomId": {"FNumber": "BOM001"}
    },
    "need_update_fields": [],
    "is_delete_entry": true
  }
}
```

### 返回结果

```json
{
  "op": "save",
  "success": true,
  "fid": "100013",
  "bill_no": "MO2026040013",
  "next_action": "submit",
  "next_action_desc": "建议调用 kingdee_submit_bills 提交单据至审核队列",
  "tip": "生产订单已保存为草稿，需要提交+审核后才能生效"
}
```

---

## 4. 提交和审核生产订单

### 提交

```json
{
  "tool": "kingdee_submit_production_orders",
  "params": {
    "bill_ids": ["100013"]
  }
}
```

### 返回结果

```json
{
  "op": "submit",
  "success": true,
  "bill_ids": ["100013"],
  "next_action": "audit",
  "next_action_desc": "建议调用 kingdee_audit_bills 审核单据",
  "tip": "生产订单已提交，请在审核通过后调用 kingdee_audit_production_orders 审核"
}
```

### 审核

```json
{
  "tool": "kingdee_audit_production_orders",
  "params": {
    "bill_ids": ["100013"]
  }
}
```

### 返回结果

```json
{
  "op": "audit",
  "success": true,
  "bill_ids": ["100013"],
  "next_action": null,
  "tip": "生产订单已审核生效。如需修改，请先调用 kingdee_unaudit_bills 反审核"
}
```

---

## 5. 生产订单下推领料单

### 用户提问

```
帮我把生产订单 MO2026040001 下推生成领料单。
```

### AI 调用

```json
{
  "tool": "kingdee_push_production_pick",
  "params": {
    "source_bill_nos": ["MO2026040001"],
    "enable_default_rule": true
  }
}
```

### 返回结果

```json
{
  "op": "push",
  "success": true,
  "source_bill_nos": ["MO2026040001"],
  "source_form_id": "PRD_MO",
  "target_form_id": "PRD_PickMtrl",
  "target_bill_nos": ["LLD2026040001"],
  "target_fids": ["200001"],
  "next_action": "submit+audit",
  "next_action_desc": "生产领料单已生成，请依次调用 kingdee_submit_bills + kingdee_audit_bills",
  "tip": "已生成 1 张生产领料单，请依次调用 kingdee_submit_bills + kingdee_audit_bills 完成提交和审核"
}
```

---

## 6. 生产领料单下推开入库单

### 用户提问

```
帮我把生产领料单 LLD2026040001 下推生成产品入库单。
```

### AI 调用

```json
{
  "tool": "kingdee_push_production_stock_in",
  "params": {
    "source_form_id": "PRD_PickMtrl",
    "source_bill_nos": ["LLD2026040001"],
    "enable_default_rule": true
  }
}
```

### 返回结果

```json
{
  "op": "push",
  "success": true,
  "source_bill_nos": ["LLD2026040001"],
  "source_form_id": "PRD_PickMtrl",
  "target_form_id": "PRD_Instock",
  "target_bill_nos": ["RKD2026040001"],
  "target_fids": ["300001"],
  "next_action": "submit+audit",
  "next_action_desc": "产品入库单已生成，请依次调用 kingdee_submit_bills + kingdee_audit_bills",
  "tip": "已生成 1 张产品入库单，请依次调用 kingdee_submit_bills + kingdee_audit_bills 完成提交和审核"
}
```

---

## 7. 生产订单直接下推开入库单

### 用户提问

```
直接下推生产订单 MO2026040002 生成产品入库单。
```

### AI 调用

```json
{
  "tool": "kingdee_push_production_stock_in",
  "params": {
    "source_form_id": "PRD_MO",
    "source_bill_nos": ["MO2026040002"],
    "enable_default_rule": true
  }
}
```

### 返回结果

```json
{
  "op": "push",
  "success": true,
  "source_bill_nos": ["MO2026040002"],
  "source_form_id": "PRD_MO",
  "target_form_id": "PRD_Instock",
  "target_bill_nos": ["RKD2026040002"],
  "target_fids": ["300002"],
  "next_action": "submit+audit",
  "next_action_desc": "产品入库单已生成，请依次调用 kingdee_submit_bills + kingdee_audit_bills",
  "tip": "已生成 1 张产品入库单，请依次调用 kingdee_submit_bills + kingdee_audit_bills 完成提交和审核"
}
```

---

## 8. 查询生产领料单

### 用户提问

```
帮我查询已审核的生产领料单。
```

### AI 调用

```json
{
  "tool": "kingdee_query_production_pick_materials",
  "params": {
    "filter_string": "FDocumentStatus='C'",
    "order_string": "FDate DESC",
    "limit": 20
  }
}
```

### 返回结果

```json
{
  "count": 3,
  "has_more": false,
  "data": [
    {
      "FID": "200001",
      "FBillNo": "LLD2026040001",
      "FDate": "2026-04-20",
      "FDocumentStatus": "C",
      "FMoBillNo": "MO2026040001",
      "FMaterialId.FNumber": "MAT002",
      "FMaterialId.FName": "原材料B",
      "FPickQty": 50,
      "FStockId.FName": "原材料仓"
    }
  ]
}
```

---

## 9. 查询产品入库单

### 用户提问

```
帮我查询最近的产品入库单。
```

### AI 调用

```json
{
  "tool": "kingdee_query_production_stock_in",
  "params": {
    "order_string": "FDate DESC",
    "limit": 20
  }
}
```

### 返回结果

```json
{
  "count": 2,
  "has_more": false,
  "data": [
    {
      "FID": "300001",
      "FBillNo": "RKD2026040001",
      "FDate": "2026-04-25",
      "FDocumentStatus": "C",
      "FMoBillNo": "MO2026040001",
      "FMaterialId.FNumber": "MAT001",
      "FMaterialId.FName": "产品A",
      "FInQty": 100,
      "FStockId.FName": "成品仓"
    }
  ]
}
```

---

## 注意事项

1. **生产订单必须审核后才能下推**：源单据状态必须是"已审核"（FDocumentStatus='C'）
2. **下推后需要提交+审核**：生成的目标单据是草稿状态，必须完成提交和审核
3. **使用 enable_default_rule**：生产环境中建议使用 `enable_default_rule=true` 让系统自动选择转换规则
4. **指定 rule_id**：如果默认规则下推失败，可以尝试显式指定 `rule_id`
5. **检查关联数量**：生产订单的累计领料数量（FPickMtrlQty）和累计入库数量（FStockInQty）不能超过订单数量

---

## 10. 查询生产汇报单

### 用户提问

```
帮我查询本月的生产汇报单。
```

### AI 调用

```json
{
  "tool": "kingdee_query_production_reports",
  "params": {
    "filter_string": "FDate>='2026-04-01' and FDate<='2026-04-30'",
    "order_string": "FDate DESC",
    "limit": 20
  }
}
```

### 返回结果

```json
{
  "count": 3,
  "has_more": false,
  "data": [
    {
      "FID": "400001",
      "FBillNo": "SCBG2026040001",
      "FDate": "2026-04-20",
      "FDocumentStatus": "C",
      "FMoBillNo": "MO2026040001",
      "FReportQty": 50,
      "FPassQty": 48,
      "FFailQty": 2
    }
  ]
}
```

### filter_string 示例

```
FDocumentStatus='C'                    -- 已审核
FMoBillNo='MO2026040001'               -- 指定生产订单
FDate>='2026-04-01'                    -- 本月
FReportType=1                          -- 汇报类型
```

### 推荐 field_keys

```
FID,FBillNo,FDate,FDocumentStatus,FMoBillNo,FReportQty,FPassQty,FFailQty,FWorkShopId.FName
```

---

## 11. 查询 MRP 运算结果

### 用户提问

```
帮我查询本月的MRP运算结果，看看有哪些物料需要采购或生产。
```

### AI 调用

```json
{
  "tool": "kingdee_query_mrp_results",
  "params": {
    "filter_string": "FDocumentStatus='C'",
    "order_string": "FPriority ASC, FSupplyDate ASC",
    "limit": 50
  }
}
```

### 返回结果

```json
{
  "count": 15,
  "has_more": true,
  "data": [
    {
      "FID": "500001",
      "FBillNo": "MRP2026040001",
      "FDate": "2026-04-15",
      "FDocumentStatus": "C",
      "FMaterialId.FNumber": "MAT001",
      "FMaterialId.FName": "原材料A",
      "FDemandQty": 1000,
      "FSupplyQty": 500,
      "FGapQty": 500,
      "FSupplyType": "Purchase",
      "FSupplyDate": "2026-04-25"
    }
  ]
}
```

### filter_string 示例

```
FDocumentStatus='C'                            -- 已审核
FMaterialId.FNumber='MAT001'                    -- 指定物料
FSupplyType='Purchase'                         -- 采购供给
FSupplyType='Production'                       -- 生产供给
FGapQty>0                                      -- 有缺口
FPriority=1                                    -- 高优先级
FSupplyDate>='2026-04-01'                     -- 指定供应日期
```

### 推荐 field_keys

```
FID,FBillNo,FDate,FDocumentStatus,FMaterialId.FNumber,FMaterialId.FName,FDemandQty,FSupplyQty,FGapQty,FSupplyType,FSupplyDate,FPriority
```

### 字段说明

| 字段 | 含义 |
|------|------|
| FDemandQty | 需求数量 |
| FSupplyQty | 供给数量（已有供给） |
| FGapQty | 缺口数量（需补充的供给） |
| FSupplyType | 供给类型（Purchase=采购, Production=生产, Transfer=调拨） |
| FSupplyDate | 建议供应日期 |
| FPriority | 优先级（数字越小优先级越高） |

---

## 快速查询汇总

### 查询生产订单进度
```json
{
  "tool": "kingdee_query_production_orders",
  "params": {
    "filter_string": "FDocumentStatus='C'",
    "field_keys": "FID,FBillNo,FMaterialId.FName,FQty,FStockInQty,FPickMtrlQty",
    "order_string": "FDate DESC",
    "limit": 20
  }
}
```

### 查询未完工的生产订单
```json
{
  "tool": "kingdee_query_production_orders",
  "params": {
    "filter_string": "FDocumentStatus='C' and FQty>FStockInQty",
    "field_keys": "FID,FBillNo,FMaterialId.FName,FQty,FStockInQty,FPlanFinishDate",
    "limit": 20
  }
}
```

### 查询领料情况
```json
{
  "tool": "kingdee_query_production_pick_materials",
  "params": {
    "filter_string": "FMoBillNo='MO2026040001'",
    "field_keys": "FID,FBillNo,FMaterialId.FName,FPickQty,FStockId.FName",
    "limit": 20
  }
}
```

### 查询入库汇总
```json
{
  "tool": "kingdee_query_production_stock_in",
  "params": {
    "filter_string": "FDocumentStatus='C'",
    "field_keys": "FID,FMoBillNo,FMaterialId.FName,FInQty,FStockId.FName",
    "order_string": "FDate DESC",
    "limit": 20
  }
}
```
