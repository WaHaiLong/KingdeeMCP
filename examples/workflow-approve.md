# 示例：审批流操作

## 用户提问

```
查一下有哪些待审批的单据。
```

## AI 调用

```json
{
  "tool": "kingdee_query_pending_approvals",
  "params": {
    "form_id": "",
    "status": "pending",
    "limit": 20
  }
}
```

## 返回结果

```json
{
  "status_filter": "pending",
  "total_forms": 2,
  "results": [
    {
      "form_id": "PUR_PurchaseOrder",
      "form_name": "采购订单",
      "count": 2,
      "data": [
        {"FID": "100015", "FBillNo": "CGRK2026030015", "FDate": "2026-03-26", "FDocumentStatus": "B"}
      ]
    },
    {
      "form_id": "SAL_SaleOrder",
      "form_name": "销售订单",
      "count": 1,
      "data": [
        {"FID": "200012", "FBillNo": "XSDD2026030012", "FDate": "2026-03-26", "FDocumentStatus": "B"}
      ]
    }
  ]
}
```

## 用户提问（审批通过）

```
审批通过这张采购订单，FID 是 100015。
```

## AI 调用（审批通过）

```json
{
  "tool": "kingdee_workflow_approve",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "bill_id": "100015",
    "action": "approve",
    "opinion": "同意"
  }
}
```

## 用户提问（驳回）

```
驳回这张销售订单，FID 是 200012，原因是数量不对。
```

## AI 调用（驳回）

```json
{
  "tool": "kingdee_workflow_approve",
  "params": {
    "form_id": "SAL_SaleOrder",
    "bill_id": "200012",
    "action": "reject",
    "opinion": "数量不对，请核对后重新提交"
  }
}
```

## 单据状态说明

| 状态码 | 含义 | 说明 |
|--------|------|------|
| Z | 暂存 | 草稿，未提交 |
| A | 创建 | 已提交，等待审核 |
| B | 审核中 | 审批流中 |
| C | 已审核 | 流程完成 |
| D | 重新审核 | 被驳回需重新审批 |

## 注意事项

- 审批流与单据审核（`kingdee_audit_bills`）是两种不同的机制：
  - **单据审核**：直接在金蝶中点击审核
  - **审批流**：走工作流审批流程，可能有多级审批节点
- 查询待审批时，如果不传 `form_id` 会查询所有支持审批流表单的待审批单据
- 驳回（reject）本质上是调用反审核（`kingdee_unaudit_bills`），将状态退回 D
