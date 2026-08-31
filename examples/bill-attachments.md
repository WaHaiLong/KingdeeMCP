# 单据附件上传与下载

依据《金蝶云星空 WebAPI 接口说明书 V6.0》的“附件上传接口（上传附件并绑定单据）”和
“附件下载接口”实现。原始说明书不随本仓库分发。

本次提供附件上传和下载，不包含独立文件上传 `UploadFile`，也不假设存在附件列表或删除 API。
工具传输 Base64 内容，不读取或写入 MCP 服务器本地文件；调用方负责文件读写和编解码。
示例编号为占位测试数据，请替换成目标账套中有权限访问的已存在单据。

## 上传表头附件

调用 `kingdee_upload_attachment`，MCP 参数格式如下。`MTIzNA==` 是文本 `1234` 的 Base64：

```json
{
  "params": {
    "form_id": "PUR_PurchaseOrder",
    "bill_id": "100723",
    "bill_no": "CGDD000198",
    "file_name": "说明.txt",
    "send_byte": "MTIzNA==",
    "is_last": true
  }
}
```

成功响应中的 `file_id` 用于下载或续传；`attachment_ids` 是 `SuccessEntitys[].Id` 中的附件内码，
与 FileId 不同。单次或最后一块成功时，`success=true`、`next_action=null`。
附件上传不会触发单据提交、审核，也不会改变单据生命周期状态。

## 分录附件与字段映射

上传分录附件时，增加 `entry_key`（例如 `FPOOrderEntry`）和 `entry_id`（例如 `101300`）。
`entry_id` 是分录内码，不是行号。表头附件不传 `entry_key`，`entry_id` 不传或传 `-1`。

| MCP 上传参数 | V6.0 字段 | 说明 |
|---|---|---|
| `form_id` | `FormId` | 必填，单据表单标识 |
| `bill_id` | `InterId` | 必填，已存在单据内码 |
| `bill_no` | `BillNO` | 必填，单据编号 |
| `file_name` | `FileName` | 必填，含扩展名的文件名；不是路径 |
| `send_byte` | `SendByte` | 必填，当前块的标准 Base64，可为空以表示空文件 |
| `is_last` | `IsLast` | 默认 true；分块时仅最后一块为 true |
| `file_id` | `FileId` | 首次不传；后续块必须使用首次响应的 FileId |
| `entry_key` | `Entrykey` | 分录附件的单据体标识 |
| `entry_id` | `EntryinterId` | 分录附件的分录内码 |
| `alias_file_name` | `AliasFileName` | 可选附件别名 |

## 分块上传

1. 将文件原始字节切为每块最多 **4 MiB**，分别编码为标准 Base64。不要添加 `data:` 前缀。
2. 第一块不传 `file_id`；还有后续块时设置 `is_last=false`。
3. 保存首次响应中的 `file_id`，后续每块均携带它。保持单据、分录及文件名一致，按顺序上传。
4. 非最后一块成功返回 `next_action="upload_attachment"`；最后一块设置 `is_last=true`，
   成功后返回 `next_action=null`。

4 MiB 是本 MCP 的单次上传限制，不是对金蝶服务端限制的声明。工具无服务端文件缓冲或自动分块，
每次调用只传一块；单据及附件权限、文件格式和大小限制仍由金蝶控制。

## 分块下载

调用 `kingdee_download_attachment`，首次 `start_index=0`：

```json
{
  "params": {
    "file_id": "23d8a447a9254a788f2d12a499898755",
    "start_index": 0
  }
}
```

响应映射：`file_part`=FilePart、`file_name`=FileName、`file_size`=FileSize（字节）、
`start_index`=StartIndex、`is_last`=IsLast。

当 `is_last=false` 时，使用**响应原样返回的** `start_index` 请求下一块，直到
`success=true` 且 `next_action=null`。不要根据已下载长度推算游标；说明书的示例中，
最终 StartIndex 可以大于 FileSize。非最后一块游标不前进时工具会报错，避免无限续传。

每块 `file_part` 应分别 Base64 解码为字节，再按顺序拼接；不要直接拼接 Base64 字符串。
调用方应核对最终字节数与 `file_size`，并把远端 `file_name` 视为不可信文件名，写入用户选定的
目标位置，避免覆盖已有文件或接受路径穿越。服务端不代替客户端保存文件。

## 失败处理与传输契约

- 保留金蝶 `ResponseStatus`、错误信息和已返回的 FileId；业务失败不自动续传。
- 上传不是幂等操作。网络中断或响应无法解析时返回 `outcome_unknown=true`，先在金蝶中核对
  附件及 FileId，不要直接重试同一块或重建附件。
- 仅 HTTP 401 自动重登重试一次；HTTP 200 业务失败（包括会话错误）、超时及其他 HTTP 错误均
  交由调用方核查处理。不会根据文件名或文件内容中的“session/会话”文字重传。
- 使用已有 ValidateUser 会话 Cookie。HTTP 请求体为 `{"data":"{...}"}`，data 的值是内层
  数据包的 JSON 字符串，不使用 Save 的 `formid`/`Model` 包装。说明书示例中的参数数组不能
  直接作为 HTTP 请求体；测试账套实测会在反序列化阶段报错。
- 端点分别为 `DynamicFormService.AttachmentUpLoad.common.kdsvc` 和
  `DynamicFormService.AttachmentDownLoad.common.kdsvc`，前缀均为
  `Kingdee.BOS.WebApi.ServicesStub.`。
- 使用日志只记录接口类型、耗时、成功状态和错误类别，不记录附件内容、文件名、FileId、会话
  或服务端响应。MCP 客户端自己的会话记录由客户端管理。

2026-08-31 已在独立测试账套完成采购订单草稿的表头附件上传、下载字节比对，并确认附件数为 1、
单据仍为创建状态。分录附件及大文件分块传输目前仍以 HTTP mock 测试验证，发布前需补充真实账套联调。
