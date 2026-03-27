# 示例：查询即时库存

## 用户提问

```
查一下所有有库存的物料，显示物料编码、名称、仓库、数量。
```

## AI 调用

```json
{
  "tool": "kingdee_query_inventory",
  "params": {
    "filter_string": "FBaseQty>0",
    "field_keys": "FMaterialId.FNumber,FMaterialId.FName,FStockId.FName,FBaseQty,FBaseUnitId.FName",
    "start_row": 0,
    "limit": 50
  }
}
```

## 返回结果

```json
{
  "count": 15,
  "data": [
    {
      "FMaterialId.FNumber": "MAT001",
      "FMaterialId.FName": "钢材 A3",
      "FStockId.FName": "A仓",
      "FBaseQty": 500.0,
      "FBaseUnitId.FName": "吨"
    },
    {
      "FMaterialId.FNumber": "MAT002",
      "FMaterialId.FName": "铝板",
      "FStockId.FName": "B仓",
      "FBaseQty": 200.0,
      "FBaseUnitId.FName": "吨"
    }
  ]
}
```

## 常用过滤条件

| 条件 | filter_string |
|------|----------------|
| 有库存（默认） | `FBaseQty>0` |
| 指定物料 | `FMaterialId.FNumber='MAT001'` |
| 指定仓库 | `FStockId.FNumber='WH01'` |
| 库存为零 | `FBaseQty=0` |
| 库存不足 | `FBaseQty<10` |

## 注意事项

- 即时库存是实时数据，反映当前账面库存
- 账面库存不等于实物库存，需结合盘点使用
- 支持按仓库、物料批次、辅助属性等进一步筛选
