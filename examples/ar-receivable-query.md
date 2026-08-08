# 应收单查询示例（AR_Receivable）

应收单记录客户应收账款，包含应收金额、已核销金额、核销状态等信息，
是营收、回款、应收余额等财务指标的核心数据来源。

> ⚠️ 不同金蝶账套字段名可能不同（如 `FCUSTOMERID` vs `FCustId`），先调用 `kingdee_get_fields('AR_Receivable')` 确认可用字段。

---

## 场景 1：查询某月已审核应收单

**用户：** 查一下 2026 年 1 月的所有已审核应收单

**AI 调用：**
```json
{
  "tool": "kingdee_query_receipts",
  "params": {
    "filter_string": "FDocumentStatus='C' and FDATE>='2026-01-01' and FDATE<='2026-01-31'",
    "field_keys": "FID,FBillNo,FDATE,FCUSTOMERID.FName,FCUSTOMERID.FNumber,FALLAMOUNTFOR,FNOTAXAMOUNTFOR,FRELATEHADPAYAMOUNT,FWRITTENOFFSTATUS",
    "limit": 50,
    "start_row": 0
  }
}
```

**返回示例：**
```json
{
  "count": 3,
  "has_more": false,
  "data": [
    [100001, "AR00006001", "2026-01-28T00:00:00", "深圳某科技有限公司", "C001", 500000.00, 442477.88, 500000.00, "C"],
    [100002, "AR00006000", "2026-01-15T00:00:00", "杭州某电子有限公司", "C002", 200000.00, 176991.15, 100000.00, "B"],
    [100003, "AR00005999", "2026-01-10T00:00:00", "北京某集成电路公司", "C003", 300000.00, 265486.73,       0.00, "A"]
  ]
}
```

**结论：** 1 月应收单 3 笔，应收总金额 100 万元（含税），不含税 88.5 万元。其中 1 笔已全额核销（C）、1 笔部分核销（B）、1 笔未核销（A）。

---

## 场景 2：查询未核销的应收单（应收账款余额）

**用户：** 现在还有哪些应收单没核销完？按到期日排序。

**AI 调用：**
```json
{
  "tool": "kingdee_query_receipts",
  "params": {
    "filter_string": "FDocumentStatus='C' and FWRITTENOFFSTATUS in ('A','B')",
    "field_keys": "FID,FBillNo,FDATE,FCUSTOMERID.FName,FCUSTOMERID.FNumber,FALLAMOUNTFOR,FRELATEHADPAYAMOUNT,FWRITTENOFFSTATUS,FENDDATE_H",
    "order_string": "FENDDATE_H ASC",
    "limit": 50,
    "start_row": 0
  }
}
```

**说明：** `FALLAMOUNTFOR - FRELATEHADPAYAMOUNT` 即为应收账款余额（应收但尚未核销的金额）。

---

## 场景 3：查询不含税应收金额汇总（用于营收统计）

**用户：** 2026 年上半年不含税应收金额总共多少？

**AI 调用：**
```json
{
  "tool": "kingdee_query_receipts",
  "params": {
    "filter_string": "FDocumentStatus='C' and FDATE>='2026-01-01' and FDATE<='2026-06-30' and FISINIT=false",
    "field_keys": "FID,FBillNo,FDATE,FCUSTOMERID.FName,FALLAMOUNTFOR,FNOTAXAMOUNTFOR",
    "limit": 100,
    "start_row": 0
  }
}
```

**说明：** `FNOTAXAMOUNTFOR` 为不含税金额，用于核算营收（含税口径用 `FALLAMOUNTFOR`）。`FISINIT=false` 排除期初初始化单据。

---

## 常用字段说明

- `FBillNo`：应收单号（如 AR00006001）
- `FDATE`：业务日期（⚠️ 有的账套用大写 FDATE，有的用小写 FDate）
- `FCUSTOMERID.FName`：客户名称（⚠️ 有的账套用 FCustId，有的用 FCUSTOMERID）
- `FCUSTOMERID.FNumber`：客户编码
- `FALLAMOUNTFOR`：应收总金额（原币含税）
- `FNOTAXAMOUNTFOR`：应收不含税金额（原币）
- `FRELATEHADPAYAMOUNT`：已核销金额
- `FWRITTENOFFSTATUS`：核销状态（A=未核销，B=部分核销，C=完全核销）
- `FOPENSTATUS`：打开状态（A=未关闭，B=已关闭，C=部分关闭）
- `FENDDATE_H`：到期日
- `FSETTLEORGID.FName`：结算组织
- `FISINIT`：是否为初始化单据（true=期初，false=业务）
