# 示例：下推生成入库单

## 场景说明

销售订单审核后，需要下推生成销售出库单；采购订单审核后，下推生成采购入库单。

## 用户提问

```
帮我把这张销售订单（XSDD2026030001）下推出库。
```

## AI 调用

```json
{
  "tool": "kingdee_push_bill",
  "params": {
    "form_id": "SAL_SaleOrder",
    "target_form_id": "SAL_OUTSTOCK",
    "source_ids": ["200001"]
  }
}
```

## 返回结果

```json
{
  "Result": {
    "ResponseStatus": {
      "IsSuccess": true,
      "Errors": []
    },
    "Ids": ["300001"],
    "Numbers": ["XSCKD2026030001"]
  }
}
```

## 常用下推场景

| 源单据 | 目标单据 | form_id | target_form_id |
|--------|----------|---------|----------------|
| 销售订单 → 销售出库单 | SAL_SaleOrder | SAL_OUTSTOCK |
| 采购订单 → 采购入库单 | PUR_PurchaseOrder | STK_InStock |
| 采购订单 → 收料通知单 | PUR_PurchaseOrder | PUR_ReceiveBill |
| 销售订单 → 销售退货单 | SAL_SaleOrder | SAL_RETURNSTOCK |

## 多张下推

```json
{
  "tool": "kingdee_push_bill",
  "params": {
    "form_id": "SAL_SaleOrder",
    "target_form_id": "SAL_OUTSTOCK",
    "source_ids": ["200001", "200002", "200003"]
  }
}
```

## 注意事项

- 源单据必须**已审核**才能下推
- 下推后生成的目标单据是草稿状态，需要提交和审核
- 如果下推失败，检查源单据是否满足下推规则（如数量是否超出）
- 指定 `rule_ids` 可以选择特定的下推转换规则
