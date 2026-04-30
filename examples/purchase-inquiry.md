# 示例：采购询价单

## 查询采购询价单

### 用户提问

```
查一下本月所有已审核的采购询价单，显示供应商、物料、报价信息。
```

### AI 调用

```json
{
  "tool": "kingdee_query_purchase_inquiry",
  "params": {
    "filter_string": "FDocumentStatus='C' and FDate>='2026-04-01'",
    "field_keys": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FMaterialId.FName,FPrice,FQuantity,FUnitId.FName",
    "order_string": "FDate DESC",
    "start_row": 0,
    "limit": 50
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
      "FID": "100001",
      "FBillNo": "RFQ2026040001",
      "FDate": "2026-04-15",
      "FDocumentStatus": "C",
      "FSupplierId.FName": "深圳华强供应商",
      "FMaterialId.FName": "钢材 A3",
      "FPrice": "5800.00",
      "FQuantity": 100.0,
      "FUnitId.FName": "吨"
    },
    {
      "FID": "100002",
      "FBillNo": "RFQ2026040002",
      "FDate": "2026-04-12",
      "FDocumentStatus": "C",
      "FSupplierId.FName": "广州天河贸易",
      "FMaterialId.FName": "铝板",
      "FPrice": "22000.00",
      "FQuantity": 50.0,
      "FUnitId.FName": "吨"
    }
  ]
}
```

### 常用过滤条件

| 条件 | filter_string |
|------|----------------|
| 已审核 | `FDocumentStatus='C'` |
| 待处理（草稿） | `FDocumentStatus='A'` |
| 指定供应商 | `FSupplierId.FNumber='S001'` |
| 指定物料 | `FMaterialId.FNumber='MAT001'` |
| 指定日期范围 | `FDate>='2026-04-01' and FDate<='2026-04-30'` |
| 报价大于某值 | `FPrice>5000` |

---

## 查询指定询价单详情

### 用户提问

```
查一下询价单 RFQ2026040001 的完整报价信息。
```

### AI 调用

```json
{
  "tool": "kingdee_query_purchase_inquiry",
  "params": {
    "filter_string": "FBillNo='RFQ2026040001'",
    "field_keys": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FNumber,FSupplierId.FName,FMaterialId.FNumber,FMaterialId.FName,FPrice,FQuantity,FUnitId.FName,FTaxRate,FDeliveryDate,FPaymentTerm",
    "start_row": 0,
    "limit": 10
  }
}
```

### 返回结果

```json
{
  "count": 1,
  "has_more": false,
  "data": [
    {
      "FID": "100001",
      "FBillNo": "RFQ2026040001",
      "FDate": "2026-04-15",
      "FDocumentStatus": "C",
      "FSupplierId.FNumber": "S001",
      "FSupplierId.FName": "深圳华强供应商",
      "FMaterialId.FNumber": "MAT001",
      "FMaterialId.FName": "钢材 A3",
      "FPrice": "5800.00",
      "FQuantity": 100.0,
      "FUnitId.FName": "吨",
      "FTaxRate": "13",
      "FDeliveryDate": "2026-04-30",
      "FPaymentTerm": "月结30天"
    }
  ]
}
```

---

## 查询供应商报价单

### 用户提问

```
查一下 S001 供应商的已审核报价单，进行比价参考。
```

### AI 调用

```json
{
  "tool": "kingdee_query_supplier_quotes",
  "params": {
    "filter_string": "FDocumentStatus='C' and FSupplierId.FNumber='S001'",
    "field_keys": "FID,FBillNo,FDate,FSupplierId.FName,FMaterialId.FNumber,FMaterialId.FName,FPrice,FQuantity,FUnitId.FName",
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
      "FID": "200001",
      "FBillNo": "QT2026040001",
      "FDate": "2026-04-15",
      "FSupplierId.FName": "深圳华强供应商",
      "FMaterialId.FNumber": "MAT001",
      "FMaterialId.FName": "钢材 A3",
      "FPrice": "5800.00",
      "FQuantity": 100.0,
      "FUnitId.FName": "吨"
    },
    {
      "FID": "200002",
      "FBillNo": "QT2026030015",
      "FDate": "2026-03-20",
      "FSupplierId.FName": "深圳华强供应商",
      "FMaterialId.FNumber": "MAT001",
      "FMaterialId.FName": "钢材 A3",
      "FPrice": "5600.00",
      "FQuantity": 80.0,
      "FUnitId.FName": "吨"
    }
  ]
}
```

---

## 注意事项

- 采购询价单（SVM_InquiryBill/RFQ）用于向供应商询价，收集报价信息
- 供应商报价单（SVM_QuoteBill）是供应商对询价单的响应
- 询价流程：创建询价单 → 发送给供应商 → 供应商报价 → 比价分析 → 选择最优供应商 → 生成采购订单
- 关键字段：`FPrice`=单价，`FQuantity`=数量，`FTaxRate`=税率，`FDeliveryDate`=交货日期，`FPaymentTerm`=付款条件
- 可用于比价分析，参考历史报价选择最优供应商
- 单据状态：`A`=创建/草稿，`B`=审核中，`C`=已审核
