# 工作流提示（Workflow Hints）

> 按需检索的上下文片段，不是静态入口。AI 执行具体任务时按需参考。

---

## 单据生命周期状态机

```
Save(草稿) → Submit(待审核) → Audit(已审核)
                            ↑         ↓
                            Unaud it  反审核 ← (如需修改)
```

**常见目标漂移**：AI 调用 Save 后误以为操作完成。实际上 Save 只生成草稿，必须继续 Submit + Audit。

---

## 写操作完整流程（无目标漂移版）

### 新建单据（采购订单/销售订单）
```
1. kingdee_save_bill   → 草稿（响应含 next_action=submit）
2. kingdee_submit_bills → 待审核（响应含 next_action=audit）
3. kingdee_audit_bills  → 已审核 ✓
```

### 下推生成目标单据
```
1. kingdee_push_bill   → 目标单草稿（响应含 next_action=submit+audit）
2. kingdee_submit_bills → 待审核
3. kingdee_audit_bills  → 已审核 ✓
```

### 修改单据
```
1. kingdee_query_bills (或 kingdee_view_bill) → 获取 FID
2. kingdee_save_bill (model 中包含 FID) → 草稿
3. kingdee_submit_bills → 待审核
4. kingdee_audit_bills  → 已审核 ✓
```

### 反审核后修改
```
1. kingdee_unaudit_bills → 待审核状态
2. 修改内容
3. 重新 Submit + Audit
```

---

## 操作返回的结构化字段（ Harness 约束）

每次写操作返回的结构：

| 字段 | 含义 |
|------|------|
| `success` | true=成功，false=失败 |
| `bill_no` / `fid` | 单据标识 |
| `next_action` | 下一步建议（null 表示流程完成） |
| `errors` | 失败时的错误详情，含 reason+suggestion |
| `tip` | 操作提示 |

**判断操作完成的逻辑**：检查 `next_action == null` 且 `success == true`。

---

## 常见错误模式及处理

### "关联数量已达上限"（demo 环境）
- **原因**：demo 账套不支持 FLinkQty，用 FReceiveQty+FStockInQty 代替
- **查法**：`kingdee_query_purchase_order_progress` 查看实际收料/入库数量
- **绕过**：直接用 FReceiveQty+FStockInQty 判断

### "字段不存在"
- **原因**：demo 账套未启用对应模块
- **查法**：`kingdee_get_fields(form_id='xxx')` 确认实际可用字段
- **常见缺失**：FTotalAmount, FLinkQty, FBusinessClose, FFreezeStatus, FTerminateStatus

### "权限不足"
- **原因**：集成用户没有该单据的操作权限
- **处理**：联系金蝶管理员开通

### "单据状态不允许该操作"
- **原因**：当前状态无法执行该操作（如对已审核单据再次审核）
- **状态对照**：A=创建, B=审核中, C=已审核, D=重新审核, Z=暂存

### Push 转换失败
- **查法**：看 `ConvertResponseStatus` 数组中每行的 `IsSuccess` 和 `Message`
- **常见原因**：rule_id 不匹配、源单据未审核、关联数量已满

---

## 快速参考

| 操作 | 工具 | 状态变化 |
|------|------|----------|
| 新建 | `kingdee_save_bill` | → 草稿 |
| 修改 | `kingdee_save_bill`(含FID) | 草稿→草稿 |
| 提交 | `kingdee_submit_bills` | 草稿→待审核 |
| 审核 | `kingdee_audit_bills` | 待审核→已审核 |
| 反审核 | `kingdee_unaudit_bills` | 已审核→待审核 |
| 删除 | `kingdee_delete_bills` | 草稿→已删除 |
| 下推 | `kingdee_push_bill` | 源单→目标单草稿 |
| 查看 | `kingdee_view_bill` | 只读，无状态变化 |

> 参考：`src/kingdee_mcp/server.py` 中 `DOC_LIFECYCLE` 和 `KNOWN_ERROR_PATTERNS`