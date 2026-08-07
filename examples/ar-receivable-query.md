# 收款单查询示例（AR_Receivable）

收款单记录客户实际付款信息，是营收、回款、应收余额、票据占比等财务指标的核心数据来源。

---

## 场景 1：查询某月已审核收款单

**用户：** 查一下 2026 年 1 月的所有已审核收款单

**AI 调用：**
```json
{
  "tool": "kingdee_query_receipts",
  "params": {
    "filter_string": "FDocumentStatus='C' and FDate>='2026-01-01' and FDate<='2026-01-31'",
    "field_keys": "FID,FBillNo,FDate,FCustId.FName,FRealAmt,FSettleTypeId.FName,FAccountId.FName",
    "order_string": "FDate DESC",
    "limit": 50
  }
}
```

**返回示例：**
```json
{
  "count": 3,
  "has_more": false,
  "data": [
    [100123, "SKD0006001", "2026-01-28T00:00:00", "深圳某科技有限公司", 500000.00, "银行转账", "工商银行基本户"],
    [100122, "SKD0006000", "2026-01-15T00:00:00", "杭州某电子有限公司", 200000.00, "银行承兑汇票", "工商银行基本户"],
    [100121, "SKD0005999", "2026-01-10T00:00:00", "北京某集成电路公司", 300000.00, "商业承兑汇票", "招商银行基本户"]
  ]
}
```

**结论：** 1 月已审核收款单 3 笔，合计 100 万元，其中现金/转账 50 万、票据 50 万，票据占比 50%。

---

## 场景 2：区分票据回款与现金回款

**用户：** 查一下今年到现在票据回款总额和现金转账回款总额分别是多少

**操作说明：** 分两次查询，用 filter_string 分别过滤结算方式

**AI 调用（票据）：**
```json
{
  "tool": "kingdee_query_receipts",
  "params": {
    "filter_string": "FDocumentStatus='C' and FDate>='2026-01-01' and (FSettleTypeId.FName like '%承兑汇票%')",
    "field_keys": "FID,FBillNo,FDate,FCustId.FName,FRealAmt,FSettleTypeId.FName",
    "limit": 100
  }
}
```

**AI 调用（现金/转账）：**
```json
{
  "tool": "kingdee_query_receipts",
  "params": {
    "filter_string": "FDocumentStatus='C' and FDate>='2026-01-01' and (FSettleTypeId.FName like '%现金%' or FSettleTypeId.FName like '%转账%')",
    "field_keys": "FID,FBillNo,FDate,FCustId.FName,FRealAmt,FSettleTypeId.FName",
    "limit": 100
  }
}
```

**注意：** 如需精确汇总，将两次查询的 `FRealAmt` 字段值分别求和即可。若单月收款笔数超过 100，需用 `start_row` 分页拉取全量。

---

## 场景 3：查询核销未完成（应收欠款）的收款单

**用户：** 看看有哪些收款单还没有核销完

**AI 调用：**
```json
{
  "tool": "kingdee_query_receipts",
  "params": {
    "filter_string": "FDocumentStatus='C' and FCloseStatus='A'",
    "field_keys": "FID,FBillNo,FDate,FCustId.FName,FCustId.FNumber,FRealAmt,FWriteOffAmt,FSettleTypeId.FName",
    "order_string": "FDate ASC",
    "limit": 50
  }
}
```

**返回示例：**
```json
{
  "count": 2,
  "has_more": false,
  "data": [
    [100080, "SKD0005800", "2025-11-05T00:00:00", "某客户A", "C001", 150000.00, 100000.00, "银行转账"],
    [100095, "SKD0005850", "2025-12-12T00:00:00", "某客户B", "C002",  80000.00,       0.00, "商业承兑汇票"]
  ]
}
```

**说明：** `FRealAmt - FWriteOffAmt` 即为未核销余额（尚未匹配到应收账款的金额）。

---

## 常用字段说明

- `FBillNo`：收款单号（如 SKD0006001）
- `FDate`：收款日期
- `FCustId.FName`：客户名称
- `FCustId.FNumber`：客户编码
- `FRealAmt`：实收金额（本次实际到账金额）
- `FWriteOffAmt`：已核销金额（已匹配到应收账款的部分）
- `FSettleTypeId.FName`：结算方式（现金 / 银行转账 / 商业承兑汇票 / 银行承兑汇票）
- `FAccountId.FName`：收款账户名称
- `FCloseStatus`：关闭状态（A=核销未完成，B=全额核销已关闭）
- `FExchangeRate`：汇率（多币别收款时使用）
- `FCurrencyId.FName`：币别名称
- `FSaleOrgId.FName`：销售组织名称
