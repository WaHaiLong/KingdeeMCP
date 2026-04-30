# 示例：调拨申请单

## 查询调拨申请单

### 用户提问

```
查一下本月所有已审核的调拨申请单，显示调出仓库、调入仓库信息。
```

### AI 调用

```json
{
  "tool": "kingdee_query_stock_transfer_apply",
  "params": {
    "filter_string": "FDocumentStatus='C' and FDate>='2026-04-01'",
    "field_keys": "FID,FBillNo,FDate,FDocumentStatus,FSendStockId.FName,FReceiveStockId.FName,FMaterialId.FName,FTransferQty",
    "order_string": "FDate DESC",
    "start_row": 0,
    "limit": 50
  }
}
```

### 返回结果

```json
{
  "count": 4,
  "has_more": false,
  "data": [
    {
      "FID": "100001",
      "FBillNo": "DB2026040001",
      "FDate": "2026-04-20",
      "FDocumentStatus": "C",
      "FSendStockId.FName": "A仓",
      "FReceiveStockId.FName": "B仓",
      "FMaterialId.FName": "钢材 A3",
      "FTransferQty": 50.0
    },
    {
      "FID": "100002",
      "FBillNo": "DB2026040002",
      "FDate": "2026-04-18",
      "FDocumentStatus": "C",
      "FSendStockId.FName": "B仓",
      "FReceiveStockId.FName": "C仓",
      "FMaterialId.FName": "铝板",
      "FTransferQty": 30.0
    }
  ]
}
```

### 常用过滤条件

| 条件 | filter_string |
|------|----------------|
| 已审核 | `FDocumentStatus='C'` |
| 待审核（草稿） | `FDocumentStatus='A'` |
| 指定调出仓库 | `FSendStockId.FNumber='WH01'` |
| 指定调入仓库 | `FReceiveStockId.FNumber='WH02'` |
| 指定物料 | `FMaterialId.FNumber='MAT001'` |
| 指定日期范围 | `FDate>='2026-04-01' and FDate<='2026-04-30'` |
| 仓库间调拨 | `FSendStockId.FNumber <> FReceiveStockId.FNumber` |

---

## 查询指定调拨申请

### 用户提问

```
查一下调拨申请单 DB2026040001 的完整信息。
```

### AI 调用

```json
{
  "tool": "kingdee_query_stock_transfer_apply",
  "params": {
    "filter_string": "FBillNo='DB2026040001'",
    "field_keys": "FID,FBillNo,FDate,FDocumentStatus,FSendStockId.FNumber,FSendStockId.FName,FReceiveStockId.FNumber,FReceiveStockId.FName,FMaterialId.FNumber,FMaterialId.FName,FTransferQty,FUnitId.FName,FNote",
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
      "FBillNo": "DB2026040001",
      "FDate": "2026-04-20",
      "FDocumentStatus": "C",
      "FSendStockId.FNumber": "WH01",
      "FSendStockId.FName": "A仓",
      "FReceiveStockId.FNumber": "WH02",
      "FReceiveStockId.FName": "B仓",
      "FMaterialId.FNumber": "MAT001",
      "FMaterialId.FName": "钢材 A3",
      "FTransferQty": 50.0,
      "FUnitId.FName": "吨",
      "FNote": "生产车间调拨"
    }
  ]
}
```

---

## 仓库库存调拨查询

### 用户提问

```
查一下 A 仓有哪些物料可以调拨，显示调出仓库 A 仓、调入仓库 B 仓的调拨申请记录。
```

### AI 调用

```json
{
  "tool": "kingdee_query_stock_transfer_apply",
  "params": {
    "filter_string": "FDocumentStatus='C' and FSendStockId.FNumber='WH01'",
    "field_keys": "FID,FBillNo,FDate,FSendStockId.FName,FReceiveStockId.FName,FMaterialId.FNumber,FMaterialId.FName,FTransferQty,FUnitId.FName",
    "order_string": "FDate DESC",
    "start_row": 0,
    "limit": 50
  }
}
```

---

## 注意事项

- 调拨申请单（STK_TransferApply）用于申请仓库之间物料的转移
- 审核后的调拨申请单可下推生成调拨单（STK_TransferDirect）
- 关键字段：`FSendStockId`=调出仓库，`FReceiveStockId`=调入仓库，`FTransferQty`=调拨数量
- 单据状态：`A`=创建/草稿，`B`=审核中，`C`=已审核
- 调拨流程：创建调拨申请 → 提交 → 审核 → 下推生成调拨单 → 调拨出库 → 调拨入库
