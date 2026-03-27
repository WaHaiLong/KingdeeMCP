# 示例：新建采购订单

## 用户提问

```
帮我新建一张采购订单：
- 供应商：S001（华强物资）
- 物料：MAT001（钢材 A3）
- 数量：100
- 单价：50
- 采购部门：D001
```

## AI 调用

```json
{
  "tool": "kingdee_save_bill",
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "model": {
      "FDate": "2026-03-27",
      "FSupplierId": {"FNumber": "S001"},
      "FPurchaseDeptId": {"FNumber": "D001"},
      "FPOOrderEntry": [
        {
          "FMaterialId": {"FNumber": "MAT001"},
          "FQty": 100,
          "FPrice": 50,
          "FTaxRate": 13,
          "FUnitID": {"FNumber": "PCS"}
        }
      ]
    },
    "need_update_fields": [],
    "is_delete_entry": true
  }
}
```

## 返回结果

```json
{
  "Result": {
    "ResponseStatus": {
      "IsSuccess": true,
      "Errors": []
    },
    "FID": "100012",
    "FBillNo": "CGRK2026030012"
  }
}
```

## 注意事项

- 新建时 **不要传 FID**，修改时才需要传 FID
- `FPurchaseDeptId` 如果不知道编号，可以传 `{"FName": "采购部"}`
- `FMaterialId` 同理，可传 `{"FName": "钢材"}` 但建议用编码更准确
- 分录中 `FUnitID` 为计量单位，如不传会用物料档案默认值
- 新建后状态为"暂存"（Z），需要调用 `kingdee_submit_bills` 提交后再审核
