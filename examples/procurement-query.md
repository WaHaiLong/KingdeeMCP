# 示例：查询已审核采购订单

## 用户提问

```
帮我查一下本月（2026年3月）所有已审核的采购订单，按日期倒序排列，包含单据号、供应商名称、金额。
```

## AI 调用

```json
{
  "tool": "kingdee_query_purchase_orders",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "filter_string": "FDocumentStatus='C' and FDate>='2026-03-01' and FDate<='2026-03-31'",
    "field_keys": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FTotalAmount",
    "order_string": "FDate DESC",
    "start_row": 0,
    "limit": 20
  }
}
```

## 返回结果

```json
{
  "count": 3,
  "has_more": false,
  "data": [
    {
      "FID": "100001",
      "FBillNo": "CGRK2026030003",
      "FDate": "2026-03-15",
      "FDocumentStatus": "C",
      "FSupplierId.FName": "深圳华强供应商",
      "FTotalAmount": "15800.00"
    },
    {
      "FID": "100002",
      "FBillNo": "CGRK2026030002",
      "FDate": "2026-03-10",
      "FDocumentStatus": "C",
      "FSupplierId.FName": "广州天河贸易",
      "FTotalAmount": "9500.00"
    },
    {
      "FID": "100003",
      "FBillNo": "CGRK2026030001",
      "FDate": "2026-03-05",
      "FDocumentStatus": "C",
      "FSupplierId.FName": "东莞鹏程物资",
      "FTotalAmount": "32000.00"
    }
  ]
}
```

## 常用过滤条件

| 条件 | filter_string |
|------|----------------|
| 已审核 | `FDocumentStatus='C'` |
| 指定供应商 | `FSupplierId.FNumber='S001'` |
| 指定日期范围 | `FDate>='2026-03-01' and FDate<='2026-03-31'` |
| 指定日期之后 | `FDate>='2026-03-01'` |
| 金额大于某值 | `FTotalAmount>10000` |
| 组合条件 | `FDocumentStatus='C' and FSupplierId.FNumber='S001' and FDate>='2026-03-01'` |

## 注意事项

- `FDocumentStatus='C'` 表示已审核，`'A'` 是创建，`'B'` 是审核中，`'D'` 是重新审核
- 单据号格式因金蝶配置不同可能有差异
- `FTotalAmount` 为字符串，返回后建议转换为数字处理
