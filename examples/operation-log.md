# 示例：操作日志查询

## 查询用户操作日志

### 用户提问

```
查一下 admin 用户今天的所有操作记录。
```

### AI 调用

```json
{
  "tool": "kingdee_query_operation_logs",
  "params": {
    "user_name": "admin",
    "start_date": "2026-04-30",
    "end_date": "2026-04-30",
    "limit": 50
  }
}
```

### 返回结果

```json
{
  "form_id": "BOS_OperateLog",
  "count": 15,
  "has_more": false,
  "filter_summary": {
    "user_name": "admin",
    "date_range": "2026-04-30 ~ 2026-04-30",
    "operate_type": "全部",
    "bill_no": ""
  },
  "data": [
    {
      "FID": "500001",
      "FDATETIME": "2026-04-30 09:15:32",
      "FUSERID": "admin",
      "FCOMPUTERNAME": "DESKTOP-ABC123",
      "FCLIENTIP": "192.168.1.100",
      "FENVIRONMENT": "0",
      "FOPERATENAME": "登录",
      "FDESCRIPTION": "金蝶云星空系统",
      "FInterId": "",
      "FTimeConsuming": 1234,
      "FClientType": "Web"
    },
    {
      "FID": "500002",
      "FDATETIME": "2026-04-30 09:16:05",
      "FUSERID": "admin",
      "FCOMPUTERNAME": "DESKTOP-ABC123",
      "FCLIENTIP": "192.168.1.100",
      "FENVIRONMENT": "1",
      "FOPERATENAME": "进入业务对象",
      "FDESCRIPTION": "采购订单",
      "FInterId": "",
      "FTimeConsuming": 0,
      "FClientType": "Web"
    },
    {
      "FID": "500003",
      "FDATETIME": "2026-04-30 09:20:18",
      "FUSERID": "admin",
      "FCOMPUTERNAME": "DESKTOP-ABC123",
      "FCLIENTIP": "192.168.1.100",
      "FENVIRONMENT": "3",
      "FOPERATENAME": "保存",
      "FDESCRIPTION": "采购订单",
      "FInterId": "CGRK2026040035",
      "FTimeConsuming": 567,
      "FClientType": "Web"
    }
  ]
}
```

### 常用过滤条件

| 条件 | 参数 |
|------|------|
| 指定用户 | `user_name: "admin"` |
| 指定日期范围 | `start_date: "2026-04-01", end_date: "2026-04-30"` |
| 指定单据号 | `bill_no: "CGRK2026040001"` |
| 指定操作类型 | `operate_type: "Save"` |
| 指定表单名称 | `form_name: "采购订单"` |

---

## 查询单据操作记录

### 用户提问

```
查一下采购订单 CGRK2026040001 的所有操作记录，看看是谁在什么时间操作过。
```

### AI 调用

```json
{
  "tool": "kingdee_query_operation_logs",
  "params": {
    "bill_no": "CGRK2026040001",
    "limit": 50
  }
}
```

### 返回结果

```json
{
  "form_id": "BOS_OperateLog",
  "count": 4,
  "has_more": false,
  "filter_summary": {
    "user_name": "",
    "date_range": "全部",
    "operate_type": "全部",
    "bill_no": "CGRK2026040001"
  },
  "data": [
    {
      "FID": "500010",
      "FDATETIME": "2026-04-28 14:30:15",
      "FUSERID": "zhangsan",
      "FCOMPUTERNAME": "PC-ZHANGSAN",
      "FCLIENTIP": "192.168.1.105",
      "FENVIRONMENT": "3",
      "FOPERATENAME": "保存",
      "FDESCRIPTION": "采购订单",
      "FInterId": "CGRK2026040001",
      "FTimeConsuming": 890,
      "FClientType": "Web"
    },
    {
      "FID": "500011",
      "FDATETIME": "2026-04-28 14:32:00",
      "FUSERID": "zhangsan",
      "FCOMPUTERNAME": "PC-ZHANGSAN",
      "FCLIENTIP": "192.168.1.105",
      "FENVIRONMENT": "3",
      "FOPERATENAME": "提交",
      "FDESCRIPTION": "采购订单",
      "FInterId": "CGRK2026040001",
      "FTimeConsuming": 456,
      "FClientType": "Web"
    },
    {
      "FID": "500012",
      "FDATETIME": "2026-04-28 15:00:22",
      "FUSERID": "lisi",
      "FCOMPUTERNAME": "LAPTOP-LISI",
      "FCLIENTIP": "192.168.1.110",
      "FENVIRONMENT": "3",
      "FOPERATENAME": "审核",
      "FDESCRIPTION": "采购订单",
      "FInterId": "CGRK2026040001",
      "FTimeConsuming": 234,
      "FClientType": "Web"
    }
  ]
}
```

---

## 安全审计：查询异常登录

### 用户提问

```
查一下本月所有登录和登出记录，排查是否有异常访问。
```

### AI 调用

```json
{
  "tool": "kingdee_query_operation_logs",
  "params": {
    "start_date": "2026-04-01",
    "end_date": "2026-04-30",
    "operate_type": "登录",
    "limit": 200
  }
}
```

### 返回结果

```json
{
  "form_id": "BOS_OperateLog",
  "count": 45,
  "has_more": false,
  "filter_summary": {
    "user_name": "",
    "date_range": "2026-04-01 ~ 2026-04-30",
    "operate_type": "登录",
    "bill_no": ""
  },
  "data": [
    {
      "FID": "500020",
      "FDATETIME": "2026-04-01 08:30:00",
      "FUSERID": "admin",
      "FCOMPUTERNAME": "DESKTOP-SERVER01",
      "FCLIENTIP": "192.168.1.10",
      "FENVIRONMENT": "0",
      "FOPERATENAME": "登录",
      "FDESCRIPTION": "金蝶云星空系统",
      "FInterId": "",
      "FTimeConsuming": 1500,
      "FClientType": "Web"
    }
  ]
}
```

---

## 操作类型说明

| FENVIRONMENT | 操作场景 | 说明 |
|--------------|----------|------|
| 0 | 登入系统 | 用户登录 |
| 1 | 进入业务对象 | 打开某个业务模块/表单 |
| 3 | 业务操作 | 保存、提交、审核、删除等操作 |
| 4 | 登出系统 | 用户登出 |

### 常用操作类型（FOPERATENAME）

- `登录` - 系统登录
- `登出` - 系统登出
- `进入业务对象` - 打开业务模块
- `保存` - 保存单据
- `提交` - 提交单据
- `审核` - 审核单据
- `反审核` - 反审核单据
- `删除` - 删除单据
- `单据查询` - 查询单据
- `批量保存` - 批量操作

---

## 注意事项

- 操作日志（BOS_OperateLog）记录用户在系统中的所有操作
- 主要用途：
  - **故障排查**：追踪某张单据的操作历史
  - **安全审计**：检查异常登录或批量操作
  - **合规要求**：追溯敏感操作记录
- 日期参数格式：`YYYY-MM-DD`
- 不传日期参数则查询全部记录
- 日志保留期限取决于金蝶系统配置，通常保留一段时间后会自动清理
- `FTimeConsuming` 单位为毫秒，可用于分析操作性能
