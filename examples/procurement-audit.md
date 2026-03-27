# 示例：批量审核单据

## 用户提问

```
审核这几张采购入库单：100001, 100002, 100003
```

## AI 调用

### 第一步：提交（如果是草稿状态）

```json
{
  "tool": "kingdee_submit_bills",
  "params": {
    "form_id": "STK_InStock",
    "bill_ids": ["100001", "100002", "100003"]
  }
}
```

### 第二步：审核

```json
{
  "tool": "kingdee_audit_bills",
  "params": {
    "form_id": "STK_InStock",
    "bill_ids": ["100001", "100002", "100003"]
  }
}
```

## 返回结果

```json
{
  "ResponseStatus": {
    "IsSuccess": true,
    "Errors": []
  },
  "Ids": ["100001", "100002", "100003"]
}
```

## 完整流程

```
草稿(Z) → 提交 → 审核中(B) → 审核 → 已审核(C)
                              ↓
                           反审核(D)
```

| 操作 | 工具 | 状态变化 |
|------|------|----------|
| 提交 | `kingdee_submit_bills` | Z → B |
| 审核 | `kingdee_audit_bills` | B → C |
| 反审核 | `kingdee_unaudit_bills` | C → B 或 D |
| 删除 | `kingdee_delete_bills` | 仅 Z 可删 |

## 注意事项

- 审核之前要先确认单据状态，已审核的不能重复审核
- 批量审核时如果其中一张有权限问题，整批可能失败，建议逐张处理
- 如果金蝶开启了审批流（Workflow），审核可能需要工作流审批，不仅仅是单据审核
