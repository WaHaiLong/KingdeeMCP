# 示例：查询物料档案

## 用户提问

```
搜索一下"钢材"相关的物料档案。
```

## AI 调用

```json
{
  "tool": "kingdee_query_materials",
  "params": {
    "filter_string": "FName like '%钢材%'",
    "field_keys": "FMaterialId,FNumber,FName,FSpecification,FUnitId.FName,FMaterialGroup.FName",
    "start_row": 0,
    "limit": 20
  }
}
```

## 返回结果

```json
{
  "count": 5,
  "data": [
    {
      "FMaterialId": "10001",
      "FNumber": "MAT001",
      "FName": "钢材 A3",
      "FSpecification": "10mm",
      "FUnitId.FName": "吨",
      "FMaterialGroup.FName": "金属材料"
    }
  ]
}
```

## 常用过滤条件

| 条件 | filter_string |
|------|----------------|
| 按编码前缀 | `FNumber like 'HG%'` |
| 按名称模糊 | `FName like '%钢板%'` |
| 按物料组 | `FMaterialGroup.FNumber='G01'` |
| 已审核启用 | `FDocumentStatus='C'` |
| 组合 | `FNumber like 'HG%' and FDocumentStatus='C'` |

## 先探索再查询

不知道确切名称时，可以先用 `kingdee_list_forms` 找 form_id，再用 `kingdee_query_materials` 查询：

```
先帮我搜一下物料档案里有哪些物料。
→ AI 调用 kingdee_list_forms 返回物料相关 form_id
→ 再问：查一下以"钢"开头的物料
```

## 注意事项

- 物料编码（FNumber）具有唯一性，查询时优先用编码
- 物料名称（FName）可能重复，修改单据时建议用编码
