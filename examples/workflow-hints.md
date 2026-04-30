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

## 高层工具优先（一站式复合）

无需中间校验时，**优先调用复合工具**，可避免漏掉 Submit/Audit 造成的目标漂移：

| 场景 | 高层工具 | 等价手工链路 |
|------|----------|---------------|
| 新建并审核 | `kingdee_create_and_audit` | save → submit → audit |
| 下推并审核 | `kingdee_push_and_audit` | push → submit → audit |

**halt-on-failure 语义**：任意一步失败立即停止，返回 `halted_at` 和 `recovery_hint` 告诉 AI 该手动调哪个工具续接。**不会自动重试**，因为业务错误（关联数量已达上限、业务关闭等）需要人工判断而非机械重试。

**何时退回手工链路**：需要在中间步骤（Save 后、Submit 后）做自定义校验、逐张人工 review、或针对失败做特殊清理时。

```
# 推荐：一次调用走完
kingdee_create_and_audit(form_id, model)            → success=true, halted_at=null
kingdee_push_and_audit(form_id, source_bill_nos, ...) → 目标单已审核生效
```

---

## 写操作完整流程（手工链路 / 需细粒度控制时）

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
| **新建并审核** | `kingdee_create_and_audit` | → 已审核（一站式） |
| **下推并审核** | `kingdee_push_and_audit` | 源单→目标单已审核（一站式） |

> 参考：`src/kingdee_mcp/server.py` 中 `DOC_LIFECYCLE`、`KNOWN_ERROR_PATTERNS`、`KNOWN_ERROR_NEXT_ACTIONS`

---

## 错误响应中的 `matched.next_action_tool`

错误若命中 `KNOWN_ERROR_PATTERNS`，会在 `errors[].matched` 中携带建议工具：

```json
{
  "errors": [{
    "message": "FCustId 不能为空",
    "matched": {
      "reason": "必录字段缺失",
      "suggestion": "用 kingdee_get_fields 查必录项后补齐 model",
      "next_action_tool": "kingdee_get_fields",
      "next_action_args_hint": "form_id"
    }
  }]
}
```

AI 收到错误后应优先按 `next_action_tool` 调用，而非自行猜测下一步。`add_known_pattern()` 支持以可选参数注册新模式的 next-action 元数据（运行时追加，重启后失效）。