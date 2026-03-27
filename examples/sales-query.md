# 示例：查询销售订单

## 用户提问

```
查一下最近 20 条销售订单，包含客户名称和金额。
```

## AI 调用

```json
{
  "tool": "kingdee_query_sale_orders",
  "params": {
    "form_id": "SAL_SaleOrder",
    "filter_string": "",
    "field_keys": "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName,FTotalAmount",
    "order_string": "FDate DESC",
    "start_row": 0,
    "limit": 20
  }
}
```

## 返回结果

```json
{
  "count": 20,
  "has_more": true,
  "data": [
    {
      "FID": "200001",
      "FBillNo": "XSDD2026030020",
      "FDate": "2026-03-25",
      "FDocumentStatus": "C",
      "FCustId.FName": "上海客户A",
      "FTotalAmount": "28000.00"
    }
  ]
}
```

## 常用过滤条件

| 条件 | filter_string |
|------|----------------|
| 已审核 | `FDocumentStatus='C'` |
| 未提交 | `FDocumentStatus='Z'` |
| 指定客户 | `FCustId.FNumber='C001'` |
| 本月 | `FDate>='2026-03-01' and FDate<='2026-03-31'` |

## 注意事项

- 销售订单和采购订单结构类似，审核流程相同
- 销售订单常配合 `kingdee_push_bill` 下推出库单
