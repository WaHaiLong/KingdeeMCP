# 示例：查询客户与供应商档案

## 用户提问（客户）

```
查一下编码为 C001 的客户信息。
```

## AI 调用（客户）

```json
{
  "tool": "kingdee_query_partners",
  "params": {
    "partner_type": "BD_Customer",
    "filter_string": "FNumber='C001'",
    "field_keys": "FCustomerId,FNumber,FName,FShortName,FContact,FPhone",
    "start_row": 0,
    "limit": 10
  }
}
```

## 用户提问（供应商）

```
查一下编码为 S001 的供应商信息。
```

## AI 调用（供应商）

```json
{
  "tool": "kingdee_query_partners",
  "params": {
    "partner_type": "BD_Supplier",
    "filter_string": "FNumber='S001'",
    "field_keys": "FSupplierId,FNumber,FName,FShortName,FContact,FPhone",
    "start_row": 0,
    "limit": 10
  }
}
```

## 返回结果

```json
{
  "type": "BD_Customer",
  "count": 1,
  "data": [
    {
      "FCustomerId": "50001",
      "FNumber": "C001",
      "FName": "上海华通贸易有限公司",
      "FShortName": "华通贸易",
      "FContact": "张三",
      "FPhone": "021-88888888"
    }
  ]
}
```

## 常用过滤条件

| 对象 | filter_string |
|------|---------------|
| 按编码 | `FNumber='C001'` |
| 按名称模糊 | `FName like '%华通%'` |
| 按简称 | `FShortName='华通'` |

## 注意事项

- `partner_type` 必须为 `BD_Customer`（客户）或 `BD_Supplier`（供应商）
- 客户和供应商是分开的两类基础资料，不要混淆
- 新建采购订单时用供应商编码，新建销售订单时用客户编码
