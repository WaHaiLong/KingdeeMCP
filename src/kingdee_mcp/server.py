"""
金蝶云星空 MCP Server
支持模块：供应链（采购/销售）、库存（出入库/即时库存）、基础资料（物料/客户/供应商）
认证方式：私有云 WebAPI + LoginByAppSecret 登录拿 SessionId，后续请求带 Cookie
"""

import json
import os
from typing import Any, List, Optional

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

# ─────────────────────────────────────────────
# 服务器初始化
# ─────────────────────────────────────────────
mcp = FastMCP("kingdee_mcp")

# ─────────────────────────────────────────────
# 连接配置（从环境变量读取）
# ─────────────────────────────────────────────
SERVER_URL = os.getenv("KINGDEE_SERVER_URL", "http://your-server/k3cloud/")
ACCT_ID    = os.getenv("KINGDEE_ACCT_ID", "")
USERNAME   = os.getenv("KINGDEE_USERNAME", "")
APP_ID     = os.getenv("KINGDEE_APP_ID", "")
APP_SEC    = os.getenv("KINGDEE_APP_SEC", "")

# WebAPI 端点路径
_EP = {
    "login":   "Kingdee.BOS.WebApi.ServicesStub.AuthService.LoginByAppSecret.common.kdsvc",
    "query":   "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc",
    "view":    "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.View.common.kdsvc",
    "save":    "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Save.common.kdsvc",
    "submit":  "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Submit.common.kdsvc",
    "audit":   "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Audit.common.kdsvc",
    "unaudit": "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.UnAudit.common.kdsvc",
    "delete":  "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Delete.common.kdsvc",
    "push":    "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Push.common.kdsvc",
}

# Session 缓存（避免每次请求都重新登录）
_session_id: Optional[str] = None

# ─────────────────────────────────────────────
# 常用表单目录（form_id 映射）
# ─────────────────────────────────────────────
FORM_CATALOG = {
    # 基础资料
    "BD_Material": {"name": "物料", "alias": ["物料", "材料", "商品", "产品"], "fields": "FMaterialId,FNumber,FName,FSpecification,FBaseUnitId.FName"},
    "BD_Customer": {"name": "客户", "alias": ["客户", "客户档案"], "fields": "FCustId,FNumber,FName,FShortName,FContact,FPhone"},
    "BD_Supplier": {"name": "供应商", "alias": ["供应商", "供应商档案", "厂家"], "fields": "FSupplierId,FNumber,FName,FShortName,FContact,FPhone"},
    "BD_Department": {"name": "部门", "alias": ["部门", "组织"], "fields": "FDeptId,FNumber,FName,FFullName"},
    "BD_Empinfo": {"name": "员工", "alias": ["员工", "人员", "职员", "用户"], "fields": "FID,FStaffNumber"},
    "BD_Stock": {"name": "仓库", "alias": ["仓库", "库房", "仓位"], "fields": "FStockId,FNumber,FName,FGroup.FName"},
    "BD_Unit": {"name": "计量单位", "alias": ["单位", "计量单位"], "fields": "FUnitId,FNumber,FName"},
    "BD_Currency": {"name": "币别", "alias": ["币别", "货币"], "fields": "FCurrencyId,FNumber,FName,FSymbol"},

    # 采购
    "PUR_PurchaseOrder": {"name": "采购订单", "alias": ["采购订单", "采购单", "PO"], "fields": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FTotalAmount"},
    "PUR_ReceiveBill": {"name": "收料通知单", "alias": ["收料通知", "到货通知"], "fields": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName"},
    "PUR_MRB": {"name": "采购退料单", "alias": ["采购退料", "退货单"], "fields": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName"},

    # 销售
    "SAL_SaleOrder": {"name": "销售订单", "alias": ["销售订单", "销售单", "SO", "订单"], "fields": "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName,FTotalAmount"},
    "SAL_OUTSTOCK": {"name": "销售出库单", "alias": ["销售出库", "出货单", "发货单"], "fields": "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName"},
    "SAL_RETURNSTOCK": {"name": "销售退货单", "alias": ["销售退货", "退货"], "fields": "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName"},

    # 库存
    "STK_InStock": {"name": "采购入库单", "alias": ["采购入库", "入库单", "入库"], "fields": "FID,FBillNo,FDate,FDocumentStatus,FStockOrgId.FName"},
    "STK_MisDelivery": {"name": "其他出库单", "alias": ["其他出库", "杂发", "领料"], "fields": "FID,FBillNo,FDate,FDocumentStatus,FStockOrgId.FName"},
    "STK_Miscellaneous": {"name": "其他入库单", "alias": ["其他入库", "杂收"], "fields": "FID,FBillNo,FDate,FDocumentStatus,FStockOrgId.FName"},
    "STK_TransferDirect": {"name": "直接调拨单", "alias": ["调拨", "调拨单", "库存调拨"], "fields": "FID,FBillNo,FDate,FDocumentStatus"},
    "STK_Inventory": {"name": "即时库存", "alias": ["库存", "即时库存", "库存查询"], "fields": "FMaterialId.FNumber,FMaterialId.FName,FStockId.FName,FBaseQty"},
    "STK_StockCountInput": {"name": "盘点单", "alias": ["盘点", "盘点单", "库存盘点"], "fields": "FID,FBillNo,FDate,FDocumentStatus"},

    # 财务
    "AP_Payable": {"name": "应付单", "alias": ["应付", "应付单", "应付账款"], "fields": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName"},
    "AR_Receivable": {"name": "应收单", "alias": ["应收", "应收单", "应收账款"], "fields": "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName"},

    # 生产
    "PRD_MO": {"name": "生产订单", "alias": ["生产订单", "生产单", "MO", "工单"], "fields": "FID,FBillNo,FDate,FDocumentStatus,FMaterialId.FName,FQty"},
    "PRD_PickMtrl": {"name": "生产领料单", "alias": ["生产领料", "领料单"], "fields": "FID,FBillNo,FDate,FDocumentStatus"},
    "PRD_Instock": {"name": "产品入库单", "alias": ["产品入库", "完工入库"], "fields": "FID,FBillNo,FDate,FDocumentStatus"},

    # 费用报销
    "ER_ExpenseRequest": {"name": "费用申请单", "alias": ["费用申请", "申请单"], "fields": "FID,FBillNo,FDate,FDocumentStatus,FApplicantId.FName,FTotalAmount"},
    "ER_ExpenseReimburse": {"name": "费用报销单", "alias": ["费用报销", "报销单", "报销"], "fields": "FID,FBillNo,FDate,FDocumentStatus,FApplicantId.FName,FTotalReimAmount"},
}


# ─────────────────────────────────────────────
# 通用工具函数
# ─────────────────────────────────────────────

def _url(ep_key: str) -> str:
    return SERVER_URL.rstrip("/") + "/" + _EP[ep_key]


async def _login() -> str:
    """登录金蝶，返回 SessionId，失败抛异常"""
    global _session_id
    payload = {"parameters": [ACCT_ID, USERNAME, APP_ID, APP_SEC, 2052]}
    async with httpx.AsyncClient(timeout=30, proxy=None) as client:
        resp = await client.post(
            _url("login"),
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("LoginResultType") != 1:
            raise RuntimeError(f"金蝶登录失败: {data.get('Message', '未知错误')}")
        _session_id = data["KDSVCSessionId"]
        return _session_id


async def _post(ep_key: str, payload: Any) -> Any:
    """带自动重新登录的 API 调用"""
    global _session_id

    # 构建金蝶 WebAPI 请求数据
    # payload 格式: [FormId, {参数对象}]
    if isinstance(payload, list) and len(payload) == 2:
        form_id, params = payload
        request_data = {"FormId": form_id, **params}
    else:
        request_data = payload

    async def _do_post(session: str) -> httpx.Response:
        return await client.post(
            _url(ep_key),
            data={"data": json.dumps(request_data)},
            headers={
                "Cookie": f"kdservice-sessionid={session}",
            },
        )

    async with httpx.AsyncClient(timeout=30, proxy=None) as client:
        # 没有 session 先登录
        if not _session_id:
            await _login()

        resp = await _do_post(_session_id)

        # session 过期则重新登录重试一次
        if resp.status_code == 401 or (
            resp.status_code == 200 and
            "会话" in resp.text or "session" in resp.text.lower()
        ):
            await _login()
            resp = await _do_post(_session_id)

        resp.raise_for_status()
        return resp.json()


def _rows(result: Any) -> list:
    """从 API 返回中提取数据行"""
    if isinstance(result, list):
        return result
    return result.get("Result", result.get("data", []))


def _err(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        msgs = {
            401: "认证失败，请检查 AppID/AppSec 配置。",
            403: "权限不足，请确认集成用户拥有对应单据权限。",
            404: "接口地址不存在，请检查 KINGDEE_SERVER_URL。",
            429: "请求过于频繁，请稍后重试。",
        }
        return f"错误：{msgs.get(code, f'HTTP {code} - {e.response.text[:200]}')}"
    if isinstance(e, httpx.TimeoutException):
        return "错误：请求超时，请检查服务器连通性。"
    if isinstance(e, RuntimeError):
        return f"错误：{e}"
    return f"错误：{type(e).__name__} - {e}"


def _fmt(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _query_payload(form_id: str, field_keys: str, filter_string: str,
                   order_string: str, start_row: int, limit: int) -> list:
    return [form_id, {
        "FieldKeys": field_keys,
        "FilterString": filter_string,
        "OrderString": order_string,
        "StartRow": start_row,
        "Limit": limit,
    }]


# ─────────────────────────────────────────────
# Pydantic 输入模型
# ─────────────────────────────────────────────

class QueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(..., description="单据类型标识，如 PUR_PurchaseOrder、SAL_SaleOrder、STK_InStock 等")
    filter_string: str = Field(default="", description="过滤条件，如 \"FDocumentStatus='C'\"")
    field_keys: str = Field(default="FID,FBillNo,FDate,FDocumentStatus", description="返回字段，逗号分隔")
    order_string: str = Field(default="FID DESC", description="排序条件")
    start_row: int = Field(default=0, ge=0, description="分页起始行（从0开始）")
    limit: int = Field(default=20, ge=1, le=100, description="每页条数，最大100")


class ViewInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(..., description="单据类型标识")
    bill_id: str = Field(..., description="单据内码 FID")


class SaveInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(..., description="单据类型，如 PUR_PurchaseOrder / SAL_SaleOrder")
    model: dict = Field(..., description="单据数据包 JSON，新建不传FID，修改必须传FID")
    need_update_fields: List[str] = Field(default_factory=list, description="修改时指定要更新的字段列表")
    is_delete_entry: bool = Field(default=True, description="是否删除未传内码的分录，修改时建议设为 false")


class BillIdsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(..., description="单据类型标识")
    bill_ids: List[str] = Field(..., description="单据内码 FID 列表", min_length=1)


class MaterialQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    filter_string: str = Field(default="", description="过滤条件，如 \"FNumber like 'HG%'\"")
    field_keys: str = Field(
        default="FMaterialId,FNumber,FName,FSpecification,FUnitId.FName,FMaterialGroup.FName",
        description="返回字段"
    )
    start_row: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class PartnerQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    partner_type: str = Field(..., description="BD_Customer（客户）或 BD_Supplier（供应商）")
    filter_string: str = Field(default="", description="过滤条件")
    field_keys: str = Field(
        default="FCustomerID,FNumber,FName,FShortName,FContact,FPhone",
        description="返回字段"
    )
    start_row: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class InventoryQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    filter_string: str = Field(default="FBaseQty>0", description="过滤条件，默认只取有库存的记录")
    field_keys: str = Field(
        default="FMaterialId.FNumber,FMaterialId.FName,FStockId.FName,FBaseQty,FBaseUnitId.FName",
        description="返回字段"
    )
    start_row: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


# ─────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────

@mcp.tool(
    name="kingdee_query_bills",
    annotations={"title": "通用单据查询", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_bills(params: QueryInput) -> str:
    """查询金蝶云星空任意单据列表，支持过滤、排序和分页。

    适用 form_id 示例：PUR_PurchaseOrder（采购订单）、SAL_SaleOrder（销售订单）、
    STK_InStock（采购入库）、SAL_OUTSTOCK（销售出库）、STK_MisDelivery（其他出库）。

    Returns:
        str: JSON，含 form_id / count / has_more / data 字段
    """
    try:
        result = await _post("query", _query_payload(
            params.form_id, params.field_keys, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({
            "form_id": params.form_id, "start_row": params.start_row,
            "count": len(rows), "has_more": len(rows) == params.limit, "data": rows,
        })
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_view_bill",
    annotations={"title": "查看单据详情", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_view_bill(params: ViewInput) -> str:
    """根据单据内码 FID 获取单据完整详情（含所有分录字段）。

    Returns:
        str: JSON 格式的完整单据数据
    """
    try:
        result = await _post("view", [params.form_id, {"Id": params.bill_id}])
        return _fmt(result)
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_purchase_orders",
    annotations={"title": "查询采购订单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_purchase_orders(params: QueryInput) -> str:
    """查询采购订单（PUR_PurchaseOrder）列表。

    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定供应商: "FSupplierId.FNumber='S001'"
    - 指定日期: "FDate>='2024-01-01' and FDate<='2024-12-31'"

    推荐 field_keys：
    FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FPurchaseDeptId.FName,FTotalAmount

    Returns:
        str: JSON 格式的采购订单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FTotalAmount"
        result = await _post("query", _query_payload(
            "PUR_PurchaseOrder", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_sale_orders",
    annotations={"title": "查询销售订单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_sale_orders(params: QueryInput) -> str:
    """查询销售订单（SAL_SaleOrder）列表。

    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定客户: "FCustId.FNumber='C001'"

    推荐 field_keys：
    FID,FBillNo,FDate,FDocumentStatus,FCustId.FName,FSalesOrgId.FName,FTotalAmount

    Returns:
        str: JSON 格式的销售订单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName,FTotalAmount"
        result = await _post("query", _query_payload(
            "SAL_SaleOrder", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_stock_bills",
    annotations={"title": "查询出入库单据", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_stock_bills(params: QueryInput) -> str:
    """查询出入库相关单据。

    form_id 常用取值：
    - STK_InStock:        采购入库单
    - SAL_OUTSTOCK:       销售出库单
    - STK_MisDelivery:    其他出库单
    - STK_Miscellaneous:  其他入库单
    - STK_TransferDirect: 直接调拨单

    Returns:
        str: JSON 格式的出入库单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FID,FBillNo,FDate,FDocumentStatus,FStockOrgId.FName"
        result = await _post("query", _query_payload(
            params.form_id, fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"form_id": params.form_id, "count": len(rows), "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_inventory",
    annotations={"title": "查询即时库存", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_inventory(params: InventoryQueryInput) -> str:
    """查询即时库存数量（STK_Inventory）。

    常用 filter_string：
    - 指定物料: "FMaterialId.FNumber='MAT001'"
    - 指定仓库: "FStockId.FNumber='WH01'"
    - 有库存:   "FBaseQty>0"（默认已设置）

    Returns:
        str: JSON 格式的库存列表，含物料编码、名称、仓库、数量、单位
    """
    try:
        result = await _post("query", _query_payload(
            "STK_Inventory", params.field_keys, params.filter_string,
            "FMaterialId.FNumber ASC", params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_materials",
    annotations={"title": "查询物料档案", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_materials(params: MaterialQueryInput) -> str:
    """查询物料基础资料（BD_Material）。

    常用 filter_string：
    - 按编码前缀: "FNumber like 'HG%'"
    - 按名称模糊: "FName like '%钢板%'"
    - 已审核启用: "FDocumentStatus='C'"

    Returns:
        str: JSON 格式的物料列表，含编码、名称、规格、单位、物料分组
    """
    try:
        result = await _post("query", _query_payload(
            "BD_Material", params.field_keys, params.filter_string,
            "FNumber ASC", params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_partners",
    annotations={"title": "查询客户或供应商", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_partners(params: PartnerQueryInput) -> str:
    """查询客户（BD_Customer）或供应商（BD_Supplier）基础资料。

    partner_type 取值：BD_Customer 或 BD_Supplier

    Returns:
        str: JSON 格式的客户/供应商列表，含编码、名称、简称、联系人、电话
    """
    try:
        result = await _post("query", _query_payload(
            params.partner_type, params.field_keys, params.filter_string,
            "FNumber ASC", params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"type": params.partner_type, "count": len(rows), "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_save_bill",
    annotations={"title": "新建或修改单据", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_save_bill(params: SaveInput) -> str:
    """新建或修改金蝶单据（采购订单、销售订单等）。

    - 新建：model 中不传 FID
    - 修改：model 中必须传 FID，并设置 is_delete_entry=false 防止分录被删

    新建采购订单 model 示例：
    {
      "FDate": "2024-01-15",
      "FSupplierId": {"FNumber": "S001"},
      "FPurchaseDeptId": {"FNumber": "D001"},
      "FPOOrderEntry": [
        {"FMaterialId": {"FNumber": "MAT001"}, "FQty": 100, "FPrice": 10.5, "FUnitID": {"FNumber": "PCS"}}
      ]
    }

    Returns:
        str: JSON，含新建单据的 FID 和单据编号 FBillNo
    """
    try:
        payload = [params.form_id, {
            "NeedUpDateFields": params.need_update_fields,
            "NeedReturnFields": ["FID", "FBillNo"],
            "IsDeleteEntry": params.is_delete_entry,
            "IsVerifyBaseDataField": False,
            "IsAutoSubmitAndAudit": False,
            "Model": params.model,
        }]
        result = await _post("save", payload)
        return _fmt(result)
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_submit_bills",
    annotations={"title": "提交单据", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_submit_bills(params: BillIdsInput) -> str:
    """提交单据（草稿 → 待审核）。

    Returns:
        str: 提交结果
    """
    try:
        result = await _post("submit", [params.form_id, {"Ids": ",".join(params.bill_ids)}])
        return _fmt(result)
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_audit_bills",
    annotations={"title": "审核单据", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_audit_bills(params: BillIdsInput) -> str:
    """审核单据（待审核 → 已审核）。

    Returns:
        str: 审核结果
    """
    try:
        result = await _post("audit", [params.form_id, {"Ids": ",".join(params.bill_ids)}])
        return _fmt(result)
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_unaudit_bills",
    annotations={"title": "反审核单据", "readOnlyHint": False, "destructiveHint": True,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_unaudit_bills(params: BillIdsInput) -> str:
    """反审核单据（已审核 → 待审核）。

    Returns:
        str: 反审核结果
    """
    try:
        result = await _post("unaudit", [params.form_id, {"Ids": ",".join(params.bill_ids)}])
        return _fmt(result)
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_delete_bills",
    annotations={"title": "删除单据", "readOnlyHint": False, "destructiveHint": True,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_delete_bills(params: BillIdsInput) -> str:
    """删除单据（仅草稿状态可删除）。

    Returns:
        str: 删除结果
    """
    try:
        result = await _post("delete", [params.form_id, {"Ids": ",".join(params.bill_ids)}])
        return _fmt(result)
    except Exception as e:
        return _err(e)


class PushDownInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(..., description="源单据类型，如 SAL_SaleOrder、PUR_PurchaseOrder")
    target_form_id: str = Field(..., description="目标单据类型，如 SAL_OUTSTOCK、STK_InStock")
    source_ids: List[str] = Field(..., description="源单据内码 FID 列表", min_length=1)
    rule_ids: List[str] = Field(default_factory=list, description="转换规则 ID 列表，留空使用默认规则")


@mcp.tool(
    name="kingdee_push_bill",
    annotations={"title": "下推单据", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_push_bill(params: PushDownInput) -> str:
    """将源单据下推生成目标单据（如销售订单下推销售出库单、采购订单下推采购入库单）。

    常用下推场景：
    - 销售订单 → 销售出库单:  form_id=SAL_SaleOrder,    target_form_id=SAL_OUTSTOCK
    - 采购订单 → 采购入库单:  form_id=PUR_PurchaseOrder, target_form_id=STK_InStock
    - 采购订单 → 收料通知单:  form_id=PUR_PurchaseOrder, target_form_id=PUR_ReceiveBill
    - 销售订单 → 销售退货单:  form_id=SAL_SaleOrder,    target_form_id=SAL_RETURNSTOCK

    Returns:
        str: JSON，含下推生成的目标单据 FID 和单据编号
    """
    try:
        payload = [params.form_id, {
            "TargetFormId": params.target_form_id,
            "SourceIds":    ",".join(params.source_ids),
            "RuleIds":      ",".join(params.rule_ids) if params.rule_ids else "",
        }]
        result = await _post("push", payload)
        return _fmt(result)
    except Exception as e:
        return _err(e)


# ─────────────────────────────────────────────
# 元数据查询工具
# ─────────────────────────────────────────────

class FormSearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    keyword: str = Field(default="", description="搜索关键词，如'员工'、'采购'、'库存'等，留空返回所有")


class FieldQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(..., description="表单标识，如 BD_Material、PUR_PurchaseOrder")


@mcp.tool(
    name="kingdee_list_forms",
    annotations={"title": "查询可用表单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_list_forms(params: FormSearchInput) -> str:
    """搜索金蝶系统中可用的表单类型（form_id）。

    不知道 form_id 时，先调用此工具搜索。例如：
    - 输入"员工"返回 BD_Empinfo
    - 输入"采购"返回采购相关的表单列表
    - 留空返回所有常用表单

    Returns:
        str: JSON 格式的表单列表，含 form_id、名称、推荐字段
    """
    keyword = params.keyword.lower()
    results = []

    for form_id, info in FORM_CATALOG.items():
        # 匹配名称或别名
        if not keyword or keyword in info["name"].lower() or any(keyword in alias.lower() for alias in info["alias"]):
            results.append({
                "form_id": form_id,
                "name": info["name"],
                "keywords": info["alias"],
                "recommended_fields": info["fields"]
            })

    return _fmt({
        "count": len(results),
        "tip": "使用 form_id 调用 kingdee_query_bills 查询数据，或调用 kingdee_get_fields 获取完整字段列表",
        "forms": results
    })


@mcp.tool(
    name="kingdee_get_fields",
    annotations={"title": "获取表单字段", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_get_fields(params: FieldQueryInput) -> str:
    """获取指定表单的字段列表。

    不知道查询哪些字段时，先调用此工具。返回该表单的推荐字段和使用说明。

    Returns:
        str: JSON 格式的字段信息
    """
    form_id = params.form_id
    info = FORM_CATALOG.get(form_id)

    if info:
        return _fmt({
            "form_id": form_id,
            "name": info["name"],
            "recommended_fields": info["fields"],
            "field_list": info["fields"].split(","),
            "tip": "字段格式说明：FXxx 是普通字段，FXxx.FName 是关联字段取名称，FXxx.FNumber 是取编码"
        })
    else:
        # 返回通用建议
        return _fmt({
            "form_id": form_id,
            "name": "未知表单",
            "tip": "此表单不在常用目录中，建议尝试以下通用字段：FID,FBillNo,FNumber,FName,FDate,FDocumentStatus",
            "common_fields": ["FID", "FBillNo", "FNumber", "FName", "FDate", "FDocumentStatus", "FCreateDate", "FModifyDate"]
        })


# ─────────────────────────────────────────────
# 审批流工具
# ─────────────────────────────────────────────

class WorkflowQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(default="", description="单据类型，如 ER_ExpenseReimburse（费用报销单），留空查询所有")
    status: str = Field(default="pending", description="状态：pending(待审批)、approved(已通过)、rejected(已驳回)、all(全部)")
    limit: int = Field(default=20, ge=1, le=100, description="返回数量")


class WorkflowActionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(..., description="单据类型，如 ER_ExpenseReimburse")
    bill_id: str = Field(..., description="单据内码 FID")
    action: str = Field(..., description="操作：approve(通过)、reject(驳回)")
    opinion: str = Field(default="", description="审批意见")


class WorkflowStatusInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(..., description="单据类型")
    bill_id: str = Field(..., description="单据内码 FID")


@mcp.tool(
    name="kingdee_query_pending_approvals",
    annotations={"title": "查询待审批单据", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_pending_approvals(params: WorkflowQueryInput) -> str:
    """查询待审批的单据列表。

    查询当前处于审批中状态（已提交、待审核）的单据。

    Returns:
        str: JSON 格式的待审批单据列表
    """
    try:
        # 根据状态筛选
        # 金蝶单据状态: A=创建, B=审核中, C=已审核, D=重新审核, Z=暂存
        status_filter = ""
        if params.status == "pending":
            status_filter = "FDocumentStatus IN ('A', 'B', 'D')"  # 待审批: 创建/审核中/重新审核
        elif params.status == "approved":
            status_filter = "FDocumentStatus = 'C'"  # 已审核
        elif params.status == "rejected":
            status_filter = "FDocumentStatus = 'D'"  # 重新审核（相当于驳回）
        else:
            status_filter = "1=1"

        # 如果指定了表单类型
        if params.form_id:
            form_ids = [params.form_id]
        else:
            # 默认查询常见需要审批的单据
            form_ids = [
                "PUR_PurchaseOrder",     # 采购订单
                "SAL_SaleOrder",         # 销售订单
                "STK_InStock",           # 采购入库单
            ]

        all_results = []
        for fid in form_ids:
            info = FORM_CATALOG.get(fid, {"name": fid})
            # 使用基础字段，避免字段不存在的问题
            fields = "FID,FBillNo,FDate,FDocumentStatus"

            payload = [fid, {
                "FormId": fid,
                "FieldKeys": fields,
                "FilterString": status_filter,
                "OrderString": "FDate DESC",
                "TopRowCount": params.limit
            }]

            try:
                result = await _post("query", payload)
                rows = _rows(result)
                if rows:
                    all_results.append({
                        "form_id": fid,
                        "form_name": info.get("name", fid),
                        "count": len(rows),
                        "data": rows
                    })
            except Exception:
                continue

        return _fmt({
            "status_filter": params.status,
            "total_forms": len(all_results),
            "results": all_results
        })
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_workflow_status",
    annotations={"title": "查询单据审批状态", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_workflow_status(params: WorkflowStatusInput) -> str:
    """查询单据的审批流状态。

    返回单据当前的审批状态和单据详情。

    Returns:
        str: JSON 格式的审批状态信息
    """
    try:
        # 查询单据详情
        result = await _post("view", [params.form_id, {"Id": params.bill_id}])

        if not result:
            return _fmt({"error": "单据不存在"})

        # 提取状态信息
        bill_data = result.get("Result", {}).get("Result", result)

        # 单据状态映射
        status_map = {
            "A": "创建",
            "B": "审核中",
            "C": "已审核",
            "D": "重新审核",
            "Z": "暂存"
        }

        doc_status = bill_data.get("FDocumentStatus", "")

        return _fmt({
            "form_id": params.form_id,
            "bill_id": params.bill_id,
            "document_status": doc_status,
            "status_name": status_map.get(doc_status, "未知"),
            "bill_no": bill_data.get("FBillNo", ""),
            "bill_data": bill_data
        })
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_workflow_approve",
    annotations={"title": "审批通过", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_workflow_approve(params: WorkflowActionInput) -> str:
    """审批通过单据。

    对待审批的单据执行审批通过操作。

    Returns:
        str: 审批结果
    """
    try:
        if params.action == "approve":
            # 审核通过
            result = await _post("audit", [params.form_id, {"Ids": params.bill_id}])
            action_name = "审批通过"
        elif params.action == "reject":
            # 驳回 = 反审核
            result = await _post("unaudit", [params.form_id, {"Ids": params.bill_id}])
            action_name = "审批驳回"
        else:
            return _fmt({"error": f"不支持的操作: {params.action}"})

        return _fmt({
            "action": action_name,
            "form_id": params.form_id,
            "bill_id": params.bill_id,
            "opinion": params.opinion or "无",
            "result": result
        })
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_expense_reimburse",
    annotations={"title": "查询费用报销单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_expense_reimburse(params: QueryInput) -> str:
    """查询费用报销单。

    专门用于查询费用报销单据，支持按状态、金额、日期筛选。

    Returns:
        str: JSON 格式的费用报销单列表
    """
    try:
        form_id = "ER_ExpenseReimburse"
        field_keys = params.field_keys or "FID,FBillNo,FDate,FDocumentStatus,FApplicantId.FName,FTotalReimAmount,FDescription"

        payload = [form_id, {
            "FormId": form_id,
            "FieldKeys": field_keys,
            "FilterString": params.filter_string or "",
            "OrderString": params.order_string or "FDate DESC",
            "TopRowCount": params.limit,
            "StartRow": params.start_row
        }]

        result = await _post("query", payload)
        rows = _rows(result)

        return _fmt({
            "form_id": form_id,
            "form_name": "费用报销单",
            "start_row": params.offset,
            "count": len(rows),
            "has_more": len(rows) >= params.limit,
            "data": rows
        })
    except Exception as e:
        return _err(e)


# ─────────────────────────────────────────────
# 入口函数
# ─────────────────────────────────────────────
def main():
    """MCP Server 入口点"""
    mcp.run()


if __name__ == "__main__":
    main()
