# 金蝶 MCP 使用示例

本目录包含常见业务场景的完整对话示例，帮助你快速上手。

## 目录

### 采购管理
| 场景 | 文件 |
|------|------|
| 查询已审核采购订单 | [`procurement-query.md`](./procurement-query.md) |
| 新建采购订单 | [`procurement-create.md`](./procurement-create.md) |
| 批量审核单据 | [`procurement-audit.md`](./procurement-audit.md) |

### 销售管理
| 场景 | 文件 |
|------|------|
| 查询销售订单 | [`sales-query.md`](./sales-query.md) |

### 库存管理
| 场景 | 文件 |
|------|------|
| 查询即时库存 | [`inventory-query.md`](./inventory-query.md) |
| 下推生成入库单 | [`push-stock-in.md`](./push-stock-in.md) |

### 基础资料查询
| 场景 | 文件 |
|------|------|
| 查询物料档案 | [`material-query.md`](./material-query.md) |
| 查询客户供应商 | [`partner-query.md`](./partner-query.md) |
| **filter_string/field_keys 通用示例** | [`query-examples.md`](./query-examples.md) |

### 生产管理
| 场景 | 文件 |
|------|------|
| 生产订单/领料/入库全流程 | [`production-mgmt.md`](./production-mgmt.md) |

### 质量管理
| 场景 | 文件 |
|------|------|
| 质量检验单（IQC）| [`quality-inspection.md`](./quality-inspection.md) |

### 库存管理
| 场景 | 文件 |
|------|------|
| 调拨申请单 | [`stock-transfer.md`](./stock-transfer.md) |

### 采购管理
| 场景 | 文件 |
|------|------|
| 采购询价单（RFQ）| [`purchase-inquiry.md`](./purchase-inquiry.md) |

### 系统运维
| 场景 | 文件 |
|------|------|
| 操作日志查询 | [`operation-log.md`](./operation-log.md) |

### 成本管理
| 场景 | 文件 |
|------|------|
| 存货核算/产品成本/标准成本分析 | [`cost-mgmt.md`](./cost-mgmt.md) |

### 工作流与审批
| 场景 | 文件 |
|------|------|
| 审批流操作 | [`workflow-approve.md`](./workflow-approve.md) |
| 单据生命周期与操作提示 | [`workflow-hints.md`](./workflow-hints.md) |

## 使用方式

复制示例中的用户问题，直接发给 AI（Claude、Cursor、OpenClaw 等），即可完成对应操作。

每个示例包含：
- **用户提问** — 你可以对 AI 说的话
- **调用工具** — AI 实际执行的 MCP 工具
- **返回结果** — 典型返回数据（格式参考）
- **注意事项** — 常见问题和最佳实践

## 工具使用技巧

### filter_string 常用过滤条件

```sql
-- 单据状态过滤
FDocumentStatus='C'                    -- 已审核
FDocumentStatus='A'                     -- 创建（草稿）
FDocumentStatus='B'                     -- 审核中

-- 日期范围过滤
FDate>='2026-04-01' and FDate<='2026-04-30'

-- 精确匹配
FSupplierId.FNumber='S001'
FMaterialId.FNumber='MAT001'
FBillNo='PO2026040001'

-- 模糊匹配
FMaterialId.FName like '%钢材%'
FSupplierId.FName like '%深圳%'

-- 组合条件
FDocumentStatus='C' and FDate>='2026-04-01'
```

### field_keys 常用字段组合

```sql
-- 采购订单常用字段
FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FSupplierId.FNumber,FTotalAmount,FMaterialId.FName,FMaterialId.FNumber,FQty,FReceiveQty,FStockInQty

-- 销售订单常用字段
FID,FBillNo,FDate,FDocumentStatus,FCustId.FName,FMaterialId.FName,FQty,FStockOutQty,FDeliQty,FTotalAmount

-- 生产订单常用字段
FID,FBillNo,FDate,FDocumentStatus,FMaterialId.FName,FMaterialId.FNumber,FQty,FPlanStartDate,FPlanFinishDate,FStockInQty,FPickMtrlQty

-- 库存查询常用字段
FMaterialId.FNumber,FMaterialId.FName,FStockId.FName,FBaseQty,FUnitId.FName

-- 成本查询常用字段
FMaterialId.FNumber,FMaterialId.FName,FStdCost,FLatestCost,FAvgCost,FUnitId.FName
```

### 一站式复合操作

对于新建并审核、下推并审核等常见场景，推荐使用复合工具避免漏掉 Submit/Audit：

```json
{
  "tool": "kingdee_create_and_audit",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "model": { ... }
  }
}
```

```json
{
  "tool": "kingdee_push_and_audit",
  "params": {
    "source_form_id": "PUR_PurchaseOrder",
    "source_bill_nos": ["PO2026040001"],
    "target_form_id": "STK_InStock"
  }
}
```

详见 [`workflow-hints.md`](./workflow-hints.md) 中的详细说明。
