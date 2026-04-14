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
    "source_bill_nos": ["XSDD2026030001"]
  }
}
```

## 返回结果（结构化格式）

```json
{
  "op": "push",
  "success": true,
  "source_bill_nos": ["XSDD2026030001"],
  "target_form_id": "SAL_OUTSTOCK",
  "target_bill_nos": ["XSCKD2026030001"],
  "next_action": "submit+audit",
  "next_action_desc": "目标单已生成，请依次调用 kingdee_submit_bills + kingdee_audit_bills",
  "tip": "已生成 1 张目标单据，请依次调用 kingdee_submit_bills + kingdee_audit_bills 完成提交和审核"
}
```

**关键**：下推成功≠操作完成！目标单还是草稿状态，必须继续提交+审核。

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
    "source_bill_nos": ["XSDD001", "XSDD002", "XSDD003"]
  }
}
```

## 指定转换规则

demo 环境无默认转换规则，必须显式指定 `rule_id`：

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

## 启用默认转换规则

生产环境可使用 `enable_default_rule=true`，让 Kingdee 自动选择下推规则，无需手动指定 rule_id：

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

## 保存失败时暂存

下推后若因关联数量等原因保存失败，`draft_on_fail=true` 可将目标单据转为暂存状态（无单据编号），而非直接报错：

```json
{
  "tool": "kingdee_push_bill",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "target_form_id": "STK_InStock",
    "source_bill_nos": ["CGDD000025"],
    "rule_id": "PUR_PurchaseOrder-STK_InStock",
    "draft_on_fail": true
  }
}
```

## 注意事项

- 源单据必须**已审核**才能下推
- 下推后生成的目标单据是草稿状态，需要提交和审核
- demo 环境必须指定 `rule_id`（从 `T_META_CONVERTRULE` 表查询）
- `rule_id` 和 `enable_default_rule` 互斥，不能同时使用
- 响应中 `ConvertResponseStatus` 包含每行转换结果，`ResponseStatus` 包含保存结果
