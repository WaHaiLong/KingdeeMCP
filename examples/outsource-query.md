# 委外加工订单查询示例（SUB_SubReqOrder）

委外加工订单记录外协生产任务（CP 测试、封装、FT 成品测试等），
是 WIP 在制量统计、逾期分析、回货交期预测的核心数据来源。

---

## 场景 1：查询当前所有在制的委外订单

**用户：** 现在有哪些委外订单还在制中？

**AI 调用：**
```json
{
  "tool": "kingdee_query_outsource_orders",
  "params": {
    "filter_string": "FDocumentStatus='C' and FStatus not in ('6','7')",
    "field_keys": "FID,FBillNo,FDate,FStatus,FSupplierId.FName,FMaterialId.FSpecification,FQty,FStockInQty,FNoStockInQty,FPlanFinishDate,FLot.FNumber",
    "limit": 50
  }
}
```

**返回示例：**
```json
{
  "count": 3,
  "has_more": false,
  "data": [
    [101234, "APTWW260500064", "2026-05-10T00:00:00", "1", "上海华力微电子", "APT32F004B", 682000, 0, 682000, "2026-08-15T00:00:00", "AP5E047"],
    [101235, "APTWW260500068", "2026-05-10T00:00:00", "1", "上海华力微电子", "APT32F004B", 163668, 0, 163668, "2026-08-20T00:00:00", "AP5F148"],
    [101240, "APTWW260600030", "2026-06-01T00:00:00", "1", "通富微电子",     "APT32F110A", 500000, 100000, 400000, "2026-09-01T00:00:00", "AP6A001"]
  ]
}
```

**说明：**
- `FStatus='1'` 表示开工中
- `FNoStockInQty` = 未入库在制量（682000、163668、400000 颗）
- 可据此汇总各供应商、各型号的在制总量

---

## 场景 2：查询逾期未完工的委外订单

**用户：** 哪些委外订单已经超过计划完工日还没完工？

**AI 调用：**
```json
{
  "tool": "kingdee_query_outsource_orders",
  "params": {
    "filter_string": "FDocumentStatus='C' and FPlanFinishDate<GETDATE() and FStatus not in ('3','6','7')",
    "field_keys": "FID,FBillNo,FSupplierId.FName,FMaterialId.FSpecification,FQty,FNoStockInQty,FPlanFinishDate,FLot.FNumber",
    "order_string": "FPlanFinishDate ASC",
    "limit": 50
  }
}
```

**返回示例：**
```json
{
  "count": 2,
  "has_more": false,
  "data": [
    [100900, "APTWW250900070", "华力微电子", "APT32F031A", 1326150, 212184, "2025-12-31T00:00:00", "AP5G972"],
    [101010, "APTWW260100001", "通富微电子",  "APT32F110A", 682000,  682000, "2026-03-15T00:00:00", "AP5H123"]
  ]
}
```

**说明：** 按 `FPlanFinishDate ASC` 排序，最早逾期的排最前面，便于优先跟进。

---

## 场景 3：查询指定供应商 30 天内到期的委外订单

**用户：** 华力微电子有哪些订单会在未来 30 天内到期回货？

**AI 调用：**
```json
{
  "tool": "kingdee_query_outsource_orders",
  "params": {
    "filter_string": "FDocumentStatus='C' and FStatus not in ('3','6','7') and FSupplierId.FName like '%华力%' and FPlanFinishDate>=GETDATE() and FPlanFinishDate<=DATEADD(day,30,GETDATE())",
    "field_keys": "FID,FBillNo,FSupplierId.FName,FMaterialId.FSpecification,FQty,FStockInQty,FNoStockInQty,FPlanFinishDate,FLot.FNumber,FPurOrderNo",
    "order_string": "FPlanFinishDate ASC",
    "limit": 50
  }
}
```

**返回示例：**
```json
{
  "count": 1,
  "has_more": false,
  "data": [
    [101234, "APTWW260500064", "上海华力微电子", "APT32F004B", 682000, 0, 682000, "2026-08-15T00:00:00", "AP5E047", "JAPTPO260627001"]
  ]
}
```

**说明：** `FPurOrderNo` 为关联采购订单号，可用于追溯对应的晶圆采购来源。

---

## 常用字段说明

- `FBillNo`：委外订单号（如 APTWW260500064）
- `FDate`：订单日期
- `FStatus`：执行状态（1=开工，3=完工，6=结案，7=结算）
- `FSupplierId.FName`：委外供应商名称
- `FMaterialId.FSpecification`：产品型号规格
- `FQty`：委外订单总数量（颗）
- `FStockInQty`：已入库数量
- `FNoStockInQty`：未入库在制量（= FQty - FStockInQty，可为负表示超收）
- `FPlanFinishDate`：计划完工日（逾期判断基准）
- `FLot.FNumber`：批次号（WIP 追溯用）
- `FPurOrderNo`：关联采购订单号（CP 委外反查晶圆来源）
- `F_XTR_Qty`：晶圆辅单位片数（自定义扩展字段，追加到 field_keys 即可查询）
