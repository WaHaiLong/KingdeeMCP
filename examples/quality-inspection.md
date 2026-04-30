# 示例：质量检验单

## 查询来料检验单

### 用户提问

```
查一下本月所有已审核的来料检验单，显示单据号、供应商、物料、合格数量。
```

### AI 调用

```json
{
  "tool": "kingdee_query_quality_inspections",
  "params": {
    "filter_string": "FDocumentStatus='C' and FDate>='2026-04-01'",
    "field_keys": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FMaterialId.FName,FPassQty,FFailQty,FInspectTypeId.FName",
    "order_string": "FDate DESC",
    "start_row": 0,
    "limit": 50
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
      "FID": "100001",
      "FBillNo": "IQC2026040001",
      "FDate": "2026-04-15",
      "FDocumentStatus": "C",
      "FSupplierId.FName": "深圳华强供应商",
      "FMaterialId.FName": "钢材 A3",
      "FPassQty": 98.0,
      "FFailQty": 2.0,
      "FInspectTypeId.FName": "来料检验"
    },
    {
      "FID": "100002",
      "FBillNo": "IQC2026040002",
      "FDate": "2026-04-10",
      "FDocumentStatus": "C",
      "FSupplierId.FName": "广州天河贸易",
      "FMaterialId.FName": "铝板",
      "FPassQty": 200.0,
      "FFailQty": 0.0,
      "FInspectTypeId.FName": "来料检验"
    }
  ]
}
```

### 常用过滤条件

| 条件 | filter_string |
|------|----------------|
| 已检验/已审核 | `FDocumentStatus='C'` |
| 待检验（草稿） | `FDocumentStatus='A'` |
| 合格数量大于零 | `FPassQty>0` |
| 不合格数量大于零 | `FFailQty>0` |
| 指定供应商 | `FSupplierId.FNumber='S001'` |
| 指定日期范围 | `FDate>='2026-04-01' and FDate<='2026-04-30'` |

---

## 查询质量检验单详情

### 用户提问

```
查一下检验单号 IQC2026040001 的详细信息。
```

### AI 调用

```json
{
  "tool": "kingdee_query_quality_inspection",
  "params": {
    "filter_string": "FBillNo='IQC2026040001'",
    "field_keys": "FID,FBillNo,FDate,FDocumentStatus,FInspectType,FInspectOrgId.FName,FBusinessType,FSupplierId.FName,FMaterialId.FName,FUnitId.FName,FQty,FQualifiedQty,FPassRate",
    "start_row": 0,
    "limit": 10
  }
}
```

### 返回结果

```json
{
  "form_id": "QIS_InspectBill",
  "count": 1,
  "has_more": false,
  "data": [
    {
      "FID": "100001",
      "FBillNo": "IQC2026040001",
      "FDate": "2026-04-15",
      "FDocumentStatus": "C",
      "FInspectType": "IQC",
      "FInspectOrgId.FName": "品质部",
      "FBusinessType": "PUR",
      "FSupplierId.FName": "深圳华强供应商",
      "FMaterialId.FName": "钢材 A3",
      "FUnitId.FName": "吨",
      "FQty": 100.0,
      "FQualifiedQty": 98.0,
      "FPassRate": "98.00"
    }
  ]
}
```

---

## 新建质量检验单

### 用户提问

```
新建一张来料检验单，供应商是 S001，物料 MAT001，数量 100，合格数量 98。
```

### AI 调用

```json
{
  "tool": "kingdee_save_quality_inspection",
  "params": {
    "model": {
      "FDate": "2026-04-30",
      "FInspectType": "IQC",
      "FInspectOrgId": {"FNumber": "ORG001"},
      "FBusinessType": "PUR",
      "FSupplierId": {"FNumber": "S001"},
      "FEntity": [
        {
          "FMaterialId": {"FNumber": "MAT001"},
          "FQty": 100,
          "FUnitId": {"FNumber": "PCS"},
          "FQualifiedQty": 98,
          "FUnQualifiedQty": 2
        }
      ]
    }
  }
}
```

### 返回结果

```json
{
  "success": true,
  "op": "save",
  "result": {
    "FID": 100065,
    "FBillNo": "IQC2026040065"
  },
  "tip": "质量检验单已保存为草稿，需要提交+审核后才能生效"
}
```

---

## 提交并审核质量检验单

### 用户提问

```
提交审核刚才创建的质量检验单 IQC2026040065。
```

### AI 调用

```json
{
  "tool": "kingdee_submit_quality_inspection",
  "params": {
    "bill_ids": ["100065"]
  }
}
```

### 返回结果

```json
{
  "success": true,
  "op": "submit",
  "bill_ids": ["100065"],
  "tip": "质量检验单已提交，请在审核通过后调用 kingdee_audit_quality_inspection 审核"
}
```

### 审核

```json
{
  "tool": "kingdee_audit_quality_inspection",
  "params": {
    "bill_ids": ["100065"]
  }
}
```

### 审核结果

```json
{
  "success": true,
  "op": "audit",
  "bill_ids": ["100065"],
  "tip": "质量检验单已审核通过"
}
```

---

## 注意事项

- 来料检验单（QIS_InspectBill/IQC）用于对采购物料进行入库前的质量检验
- 检验单状态：`A`=创建/草稿，`B`=审核中，`C`=已审核，`D`=重新审核
- 检验结果字段：`FPassQty`=合格数量，`FFailQty`=不合格数量，`FPassRate`=合格率
- 新建后需依次调用 `submit` 和 `audit` 才能使检验结果生效
- 审核后的检验单可关联到采购入库单，控制物料是否允许入库
