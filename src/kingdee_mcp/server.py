"""
金蝶云星空 MCP Server
支持模块：供应链（采购/销售）、库存（出入库/即时库存）、基础资料（物料/客户/供应商）
认证方式：私有云 WebAPI + LoginByAppSecret 登录拿 SessionId，后续请求带 Cookie
SQL Server 探查：系统目录只读查询，辅助理解数据库结构（可选功能）
Harness 层：操作链约束（harness/）、反馈循环、结构化退出条件、失败追溯
"""

import json
import os
import re
from typing import Any, List, Literal, Optional

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts.base import UserMessage
from pydantic import BaseModel, ConfigDict, Field

# ─────────────────────────────────────────────
# 已知错误模式库（记忆层）
# 每次遇到新错误模式后追加，格式：("错误关键词", "原因说明", "建议操作")
# ─────────────────────────────────────────────
KNOWN_ERROR_PATTERNS: List[tuple[str, str, str]] = [
    # HTTP 层
    ("502",        "金蝶不支持 HTTP/2，需显式传 http1=True",         "确保 httpx AsyncHTTPTransport(http1=True)"),
    ("Bad Gateway","同上，金蝶服务器不支持 HTTP/2",                   "同上"),
    ("会话",       "Session 过期或未登录",                            "调用 _login() 重新登录"),
    ("session",    "Session 过期（英文原文）",                         "调用 _login() 重新登录"),
    # 业务层（常见单据操作错误）
    ("关联数量",   "累计关联数量已达订单数量，无法下推",               "检查 FReceiveQty+FStockInQty 是否已满"),
    ("业务关闭",   "该行已业务关闭，不允许操作",                       "检查 FBusinessClose 状态或联系管理员反关闭"),
    ("冻结",       "分录行已冻结，不允许编辑和关联操作",               "联系管理员解冻后重试"),
    ("终止",       "分录行已终止，不允许关联操作",                     "检查 FTerminateStatus 状态"),
    ("交货数量",   "超过交货数量控制范围",                             "检查 FDlyCntl_Low/High 配置"),
    ("权限",       "集成用户没有对应单据的操作权限",                   "联系金蝶管理员开通权限"),
    ("字段不存在", "字段在当前账套/模块中未启用",                      "用 kingdee_get_fields 确认可用字段，或改用替代字段"),
    ("保存失败",   "下推或保存失败，详情见 ConvertResponseStatus",     "检查 ConvertResponseStatus 每行错误原因"),
    # 状态/并发/校验类（高频）
    ("已被其他用户修改", "乐观锁冲突，单据被并发修改",                "重新调用 kingdee_view_bill 拉最新数据再 Save"),
    ("已存在",     "唯一键冲突 (FBillNo / FNumber 重复)",              "检查是否重复 Save，或换一个编码"),
    ("不能为空",   "必录字段缺失",                                     "用 kingdee_get_fields 查必录项后补齐 model"),
    ("已审核",     "单据已审核，不允许再次提交/审核",                 "用 kingdee_unaudit_bills 反审核后再操作"),
    ("非草稿",     "单据非草稿状态，不允许 Submit",                   "确认单据状态后再决定下一步"),
    ("基础资料",   "外键引用不存在 (物料/客户/供应商/部门)",          "用 kingdee_query_materials / kingdee_query_partners 验证 FNumber"),
]

# next-action 元数据：与 KNOWN_ERROR_PATTERNS 平行，命中 pattern 时给出建议工具
# 不并入 tuple 是为了保持 add_known_pattern() 三参公共签名向后兼容
KNOWN_ERROR_NEXT_ACTIONS: dict[str, dict] = {
    "字段不存在":       {"tool": "kingdee_get_fields",                          "args_hint": "form_id"},
    "不能为空":         {"tool": "kingdee_get_fields",                          "args_hint": "form_id"},
    "已被其他用户修改": {"tool": "kingdee_view_bill",                           "args_hint": "form_id, bill_id"},
    "关联数量":         {"tool": "kingdee_query_purchase_order_progress",       "args_hint": "源单 FBillNo"},
    "基础资料":         {"tool": "kingdee_query_materials | kingdee_query_partners", "args_hint": "FNumber"},
    "已审核":           {"tool": "kingdee_unaudit_bills",                       "args_hint": "form_id, bill_ids"},
    "已存在":           {"tool": "kingdee_query_bills",                         "args_hint": "form_id, FBillNo / FNumber"},
}

# 单据操作生命周期状态机（约束层）
# 状态流转: 创建 → 提交 → 审核 → ... → 反审核(撤销)
# 目标漂移根源：AI 以为 Save=结束，实际上 Save 只到草稿状态
DOC_LIFECYCLE: dict[str, dict] = {
    # 通用写操作后的 next_action 建议
    "save":    {"from": "草稿",   "to": "草稿",   "success": True,  "next_action": "submit",  "next_action_desc": "建议调用 kingdee_submit_bills 提交单据至审核队列"},
    "submit":  {"from": "草稿",   "to": "待审核", "success": True,  "next_action": "audit",   "next_action_desc": "建议调用 kingdee_audit_bills 审核单据"},
    "audit":   {"from": "待审核", "to": "已审核", "success": True,  "next_action": None,      "next_action_desc": "操作完成，单据已生效"},
    "unaudit": {"from": "已审核", "to": "待审核", "success": True,  "next_action": None,      "next_action_desc": "已反审核，可修改后重新提交"},
    "delete":  {"from": "草稿",   "to": "已删除", "success": True,  "next_action": None,      "next_action_desc": "单据已删除"},
    "push":    {"from": "源单",   "to": "目标单草稿", "success": True, "next_action": "submit+audit", "next_action_desc": "目标单已生成，请依次调用 kingdee_submit_bills + kingdee_audit_bills"},
}

def _match_known_pattern(message: str) -> Optional[dict]:
    """对单条错误消息做 KNOWN_ERROR_PATTERNS 匹配，命中则返回结构化建议。

    返回形如 {"reason", "suggestion", "next_action_tool"?, "next_action_args_hint"?}。
    未命中返回 None。
    """
    if not message:
        return None
    msg_lower = message.lower()
    for pattern, reason, suggestion in KNOWN_ERROR_PATTERNS:
        if pattern.lower() in msg_lower:
            matched: dict = {"reason": reason, "suggestion": suggestion}
            na = KNOWN_ERROR_NEXT_ACTIONS.get(pattern)
            if na:
                matched["next_action_tool"] = na["tool"]
                matched["next_action_args_hint"] = na["args_hint"]
            return matched
    return None


def _parse_kingdee_errors(result: Any) -> list:
    """从 Kingdee API 响应中提取业务错误（反馈层核心函数）。

    返回 errors 列表，每项含 message/detail/field/matched；
    push 的 ConvertResponseStatus 逐行也会走同一套模式匹配。
    """
    errors = []
    seen: set = set()  # dedup key: (row|None, message)
    try:
        rs = result.get("Result", result) if isinstance(result, dict) else {}
        status = rs.get("ResponseStatus", {})
        if isinstance(status, dict) and not status.get("IsSuccess", True):
            for err in status.get("Errors", []):
                msg = err.get("Message", "")
                key = (None, msg)
                if key in seen:
                    continue
                seen.add(key)
                errors.append({
                    "message": msg,
                    "detail": err.get("Dsc", ""),
                    "field": err.get("FieldName", ""),
                    "matched": _match_known_pattern(msg),
                })
        # Push 操作特有的 ConvertResponseStatus —— 逐行也走 pattern 匹配
        conv = rs.get("ConvertResponseStatus", [])
        if conv:
            for i, c in enumerate(conv):
                if not c.get("IsSuccess", True):
                    msg = c.get("Message", "转换失败")
                    key = (i, msg)
                    if key in seen:
                        continue
                    seen.add(key)
                    errors.append({
                        "type": "convert",
                        "row": i,
                        "message": msg,
                        "detail": c.get("Description", ""),
                        "matched": _match_known_pattern(msg),
                    })
    except Exception:
        pass
    return errors


def _result_status(result: Any, op: str) -> dict:
    """构建结构化操作结果（约束层 + 反馈层）"""
    rs = result.get("Result", result) if isinstance(result, dict) else {}
    status = rs.get("ResponseStatus", {})

    if isinstance(status, dict):
        ok = status.get("IsSuccess", False)
        errors = _parse_kingdee_errors(result) if not ok else []
    else:
        ok = True
        errors = []

    lifecycle = DOC_LIFECYCLE.get(op, {})

    # 提取单据标识
    fid = rs.get("FID") or rs.get("Id")
    bill_no = rs.get("FBillNo") or rs.get("Number")
    ids = rs.get("Ids") or (fid if fid else None)

    out: dict[str, Any] = {
        "op": op,
        "success": ok,
        "response_status": status,
    }
    if fid:
        out["fid"] = fid
    if bill_no:
        out["bill_no"] = bill_no
    if ids:
        out["ids"] = [ids] if isinstance(ids, str) or isinstance(ids, int) else list(ids)
    if errors:
        out["errors"] = errors
        out["tip"] = (
            "单据操作失败，请检查 errors 列表中的 reason 和 suggestion 字段。"
            "如需更多信息，调用 kingdee_view_bill 查看单据详情。"
        )
    if ok:
        # next_action 始终返回（None 表示流程完成）
        out["next_action"] = lifecycle.get("next_action")
        if out["next_action"]:
            out["next_action_desc"] = lifecycle["next_action_desc"]

    return out


def add_known_pattern(
    pattern: str,
    reason: str,
    suggestion: str,
    next_action_tool: Optional[str] = None,
    next_action_args_hint: Optional[str] = None,
) -> None:
    """向已知错误模式库追加新模式（记忆层核心函数）。

    用法示例：
        add_known_pattern("特定错误关键词", "原因说明", "建议操作")
        add_known_pattern("字段A", "原因", "建议",
                          next_action_tool="kingdee_get_fields",
                          next_action_args_hint="form_id")

    next-action 元数据可选；若提供，命中此 pattern 的错误会在 matched 中携带
    next_action_tool / next_action_args_hint，方便 AI 自助恢复。
    """
    global KNOWN_ERROR_PATTERNS
    existing = [p[0] for p in KNOWN_ERROR_PATTERNS]
    if pattern not in existing:
        KNOWN_ERROR_PATTERNS.append((pattern, reason, suggestion))
    if next_action_tool:
        KNOWN_ERROR_NEXT_ACTIONS[pattern] = {
            "tool": next_action_tool,
            "args_hint": next_action_args_hint or "",
        }


def _err(e: Exception, extra_errors: list = None, op: str = "") -> str:
    """标准化错误返回（反馈层），整合 Kingdee 业务错误 + HTTP 错误

    Args:
        e: 异常对象
        extra_errors: 额外的已解析错误列表
        op: 操作类型（用于失败日志记录），如 "save" / "push" / "submit"
    """
    # 先追加已解析的金蝶业务错误
    extra = extra_errors or []

    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        msgs = {
            401: "认证失败，请检查 AppID/AppSec 配置",
            403: "权限不足，请确认集成用户拥有对应单据权限",
            404: "接口地址不存在，请检查 KINGDEE_SERVER_URL",
            429: "请求过于频繁，请稍后重试",
        }
        raw = e.response.text[:300].strip()
        err_item = {"type": "http", "code": code, "message": msgs.get(code, f"HTTP {code}"), "raw": raw}
        matched = _match_known_pattern(raw)
        if matched:
            err_item["matched"] = matched
        extra.append(err_item)
    elif isinstance(e, httpx.TimeoutException):
        extra.append({"type": "timeout", "message": "请求超时，请检查服务器连通性"})
    elif isinstance(e, RuntimeError):
        extra.append({"type": "runtime", "message": str(e)})
    else:
        extra.append({"type": "unknown", "message": f"{type(e).__name__} - {e}"})

    result = {"error": True, "errors": extra}

    # 失败追溯：记录到 failure_log.jsonl（记忆层核心）
    if op and extra:
        try:
            from scripts.failure_log import FailureLogger
            FailureLogger().log(op, result)
        except Exception:
            pass  # 不因日志记录失败影响正常返回

    return _fmt(result)


def _fmt(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)

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
LCID       = int(os.getenv("KINGDEE_LCID", "2052"))

# ─────────────────────────────────────────────
# SQL Server 探查配置（可选，从环境变量读取）
# ─────────────────────────────────────────────
_SQL_HOST     = os.getenv("MCP_SQLSERVER_HOST", "")
_SQL_PORT     = os.getenv("MCP_SQLSERVER_PORT", "1433")
_SQL_USER     = os.getenv("MCP_SQLSERVER_USER", "")
_SQL_PASSWORD = os.getenv("MCP_SQLSERVER_PASSWORD", "")
_SQL_DATABASE = os.getenv("MCP_SQLSERVER_DATABASE", "")
_SQL_SCHEMA   = os.getenv("MCP_SQLSERVER_SCHEMA", "dbo")
_SQL_ENABLED  = bool(_SQL_HOST and _SQL_USER and _SQL_PASSWORD)

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
    "user":         "Kingdee.BOS.WebApi.ServicesStub.UserService.QueryUser.common.kdsvc",
    "role":         "Kingdee.BOS.WebApi.ServicesStub.RoleService.QueryRole.common.kdsvc",
    "permission":   "Kingdee.BOS.WebApi.ServicesStub.PermissionService.QueryPermission.common.kdsvc",
    "sequence":     "Kingdee.BOS.WebApi.ServicesStub.SequenceRuleService.QuerySequenceRule.common.kdsvc",
    "number_rule":   "Kingdee.BOS.WebApi.ServicesStub.NumberRuleService.QueryNumberRule.common.kdsvc",
    "sysconfig":    "Kingdee.BOS.WebApi.ServicesStub.SystemConfigService.QuerySystemConfig.common.kdsvc",
}

# Session 缓存（避免每次请求都重新登录）
_session_id: Optional[str] = None

# ─────────────────────────────────────────────
# 常用表单目录（form_id 映射）
# 字段说明：
#   name       — 表单中文名称
#   alias      — 常用别名列表（用于 AI 理解用户意图）
#   desc       — 表单用途描述（帮助 AI 判断何时使用该表单）
#   fields     — 推荐查询字段（逗号分隔，*标记字段在某些环境可能不可用）
#   business_rules — 关键业务规则（字段→含义 / 操作限制）
#   db_tables  — 对应数据库表名（主表 + 分录表）
#
# 环境说明：
#   字段标注 [需启用供应链] 表示需要采购/库存模块启用后才存在
#   业务规则字段（如 FLinkQty/FBusinessClose）在 demo 环境可能不存在
#   💡 REMEMBER: demo 环境缺失字段：FLinkQty, FBusinessClose, FFreezeStatus, FTerminateStatus, FDlyCntl_Low/High, FCloseStatus, FTotalAmount
#   如遇字段不存在错误，请用 kingdee_get_fields(form_id) 查看实际可用字段
# ─────────────────────────────────────────────

FORM_CATALOG = {
    # ══════════════════════════════════════════════════════
    # 基础资料
    # ══════════════════════════════════════════════════════
    "BD_Material": {
        "name": "物料",
        "alias": ["物料", "材料", "商品", "产品"],
        "desc": "企业采购、生产、销售的最小存货单位，是供应链和财务核算的基础。",
        "fields": "FMaterialId,FNumber,FName,FSpecification,FUnitID.FName,FMaterialGroup.FName,FDocumentStatus",
        "db_tables": ("T_BD_MATERIAL", "T_BD_MATERIALENTRY"),
    },
    "BD_Customer": {
        "name": "客户",
        "alias": ["客户", "客户档案", "客户资料"],
        "desc": "企业销售业务中的购买方（下游）。",
        "fields": "FNumber,FName,FShortName,FContact,FPhone,FDocumentStatus",
        "db_tables": ("T_BD_CUSTOMER",),
    },
    "BD_Supplier": {
        "name": "供应商",
        "alias": ["供应商", "供应商档案", "厂家", "供货商"],
        "desc": "企业采购业务中的供应方（上游）。",
        "fields": "FSupplierId,FNumber,FName,FShortName,FContact,FPhone,FDocumentStatus",
        "db_tables": ("T_BD_SUPPLIER",),
    },
    "BD_Department": {
        "name": "部门",
        "alias": ["部门", "组织", "组织架构"],
        "desc": "企业内部组织单元，用于业务归属和权限控制。",
        "fields": "FDeptId,FNumber,FName,FFullName,FParentID.FName",
        "db_tables": ("T_BD_DEPARTMENT",),
    },
    "BD_Empinfo": {
        "name": "员工",
        "alias": ["员工", "人员", "职员", "用户", "采购员"],
        "desc": "企业职员资料，常用于采购员、销售员等业务角色指定。",
        "fields": "FID,FStaffNumber,FName,FDeptId.FName,FDocumentStatus",
        "db_tables": ("T_BD_EMPINFO",),
    },
    "BD_Stock": {
        "name": "仓库",
        "alias": ["仓库", "库房", "仓位", "库存组织"],
        "desc": "物料存储位置，是出入库和库存管理的核心维度。",
        "fields": "FStockId,FNumber,FName,FGroup.FName,FStockType.FName,FDocumentStatus",
        "db_tables": ("T_BD_STOCK",),
    },
    "BD_Unit": {
        "name": "计量单位",
        "alias": ["单位", "计量单位", "单位组"],
        "desc": "物料数量的计量标准，如个、件、箱、吨等。",
        "fields": "FUnitId,FNumber,FName,FType",
        "db_tables": ("T_BD_UNIT",),
    },
    "BD_Currency": {
        "name": "币别",
        "alias": ["币别", "货币", "币种"],
        "desc": "业务交易的货币类型，如人民币、美元等。",
        "fields": "FCurrencyId,FNumber,FName,FSymbol,FExchangeRateType",
        "db_tables": ("T_BD_CURRENCY",),
    },

    # ══════════════════════════════════════════════════════
    # 供应链：采购
    # ══════════════════════════════════════════════════════

    "PUR_PurchaseOrder": {
        "name": "采购订单",
        "alias": ["采购订单", "采购单", "PO", "采购合同订单"],
        "desc": (
            "企业与供应商的采购协议，记录货物规格、价格、交货条件，是采购业务的核心单据。"
            "与收料通知单、采购入库单、退料申请单有上下游关联关系。"
        ),
        # 注：FTotalAmount/FLinkQty/FBusinessClose 等字段在 demo 环境可能不存在，
        #     如遇字段不存在错误，请用 kingdee_get_fields 确认实际可用字段
        "fields": (
            "FID,FBillNo,FDate,FDocumentStatus,"
            "FSupplierId.FName,FSupplierId.FNumber,"
            "FPurchaseDeptId.FName,FPurchaserId.FName,"
            "FTaxAmount,FAllAmount,"
            "FMaterialId.FName,FMaterialId.FNumber,FQty,"
            "FReceiveQty,FStockInQty"
        ),
        "db_tables": ("T_PUR_PURCHASEORDER", "T_PUR_POORDERENTRY"),
        "business_rules": {
            "FReceiveQty": "累计收料数量（收料单审核时累加，反审核时扣减）",
            "FStockInQty": "累计入库数量（入库单审核时累加，反审核时扣减）",
            "FLinkQty [需启用供应链]": "关联数量 = 累计收料数量 + 累计入库数量，>=订单数量时无法下推",
            "FBusinessClose [需启用供应链]": "业务关闭状态（A=正常 B=业务关闭）",
            "FFreezeStatus [需启用供应链]": "冻结状态（A=正常 B=冻结）",
            "FTerminateStatus [需启用供应链]": "终止状态（A=正常 B=终止）",
            "FDlyCntl_Low [需启用供应链]": "交货下限，勾选控制交货数量后生效",
            "FDlyCntl_High [需启用供应链]": "交货上限，勾选控制交货数量后生效",
            "FCloseStatus [需启用供应链]": "整单关闭状态（A=未关闭 B=已关闭）",
            "下推收料通知单": "单据状态=已审核 + 关闭状态=未关闭 + 业务状态=正常 + 关联数量<订单数量",
            "下推采购入库单": "单据状态=已审核 + 关闭状态=未关闭 + 业务状态=正常 + 关联数量<订单数量 + 来料检验=未勾选",
            "交货数量控制 [需启用供应链]": "勾选后：关联数量>=交货下限无法下推；关联数量+本次>交货上限目标单据无法保存",
            "业务关闭条件 [需启用供应链]": "累计入库数量>=交货下限时，该行自动业务关闭；<交货下限自动反关闭",
            "冻结/终止限制 [需启用供应链]": "冻结或终止的分录行只允许查看、反冻结/反终止、打印、引入引出",
            "预付关联": "采购订单被付款单关联后，不可反审核",
        },
    },

    "PUR_ReceiveBill": {
        "name": "收料通知单",
        "alias": ["收料通知", "到货通知", "收料单", "来料通知"],
        "desc": (
            "供应商发货到货后创建的通知单，用于来料检验和入库准备。"
            "可直接下推采购入库单；若物料勾选来料检验，则入库必须经由收料单。"
        ),
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FStockOrgId.FName,FInspectStatus",
        "db_tables": ("T_PUR_RECEIVEBILL", "T_PUR_RECEIVEBILLENTRY"),
        "business_rules": {
            "来料检验": "物料勾选来料检验时，入库必须先收料再检验，无法直接从订单下推入库单",
            "审核更新": "收料单审核时，累加采购订单【累计收料数量】；反审核时扣减",
            "下推入库": "可下推采购入库单；下推时入库单日期须在最早/最晚交货时间内",
        },
    },

    "PUR_MRB": {
        "name": "采购退料单",
        "alias": ["采购退料", "退货单", "来料不良退货"],
        "desc": "供应商供货存在质量问题时，向供应商退货的单据。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FReturnReason,FReturnQty",
        "db_tables": ("T_PUR_MRB", "T_PUR_MRBENTRY"),
        "business_rules": {
            "退料前提": "采购订单【检验可退数量】或【库存可退数量】>0 时才可发起退料",
            "补料方式": "与采购订单关联的退料单【补料方式】必须为按原单补料",
        },
    },

    "PUR_Requisition": {
        "name": "采购申请单",
        "alias": ["采购申请", "申购单", "请购单", "采购需求"],
        "desc": (
            "企业内部各需求部门发起的采购需求，是采购流程的起点。"
            "可下推生成采购订单、采购询价单等。审核后流转至采购部门执行。"
        ),
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FApplicantId.FName,FRequestDeptId.FName,FApplicantDeptId.FName,FTotalAmount",
        "db_tables": ("T_PUR_REQUISITION", "T_PUR_REQUISITIONENTRY"),
        "business_rules": {
            "流转方向": "采购申请单 → 采购订单 或 采购询价单（RFQ）",
            "单人审核": "同一采购员同一天只能审核一张采购申请单",
        },
    },

    "PUR_MRAPP": {
        "name": "退料申请单",
        "alias": ["退料申请", "退料申请单"],
        "desc": "库存物料需要退还给供应商时，发起的退料申请。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FReturnType,FReturnQty",
        "db_tables": ("T_PUR_MRAPP", "T_PUR_MRAPPDISENTRY"),
    },

    "PUR_Contract": {
        "name": "采购合同",
        "alias": ["采购合同", "合同", "采购协议"],
        "desc": "与供应商签订的框架采购协议，可关联具体采购订单执行。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FTotalAmount,FContractStatus",
        "db_tables": ("T_PUR_CONTRACT",),
    },

    "PUR_PriceCategory": {
        "name": "采购价目表",
        "alias": ["采购价目", "采购价格", "价格资料", "供应商价格"],
        "desc": "供应商对特定物料的定价清单，采购订单可直接引用价目表价格。",
        "fields": "FID,FBillNo,FDocumentStatus,FSupplierId.FName,FMaterialId.FName,FPrice,FTaxPrice,FCurrencyId.FName",
        "db_tables": ("T_PUR_PRICECATEGORY", "T_PUR_PRICECATEGORYENTRY"),
    },

    "PUR_PAT": {
        "name": "采购调价表",
        "alias": ["采购调价", "调价表", "价格调整"],
        "desc": "调整采购价目表中物料价格的单据，有生效日期控制。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FMaterialId.FName,FOldPrice,FNewPrice,FEffectiveDate",
        "db_tables": ("T_PUR_PAT", "T_PUR_PATENTRY"),
    },

    # ══════════════════════════════════════════════════════
    # 供应链：供应商协同
    # ══════════════════════════════════════════════════════

    "SVM_InquiryBill": {
        "name": "采购询价单",
        "alias": ["询价单", "询价", "RFQ", "请求报价"],
        "desc": "向供应商发起采购询价（Request for Quotation），收集报价信息。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FExpiryDate",
        "db_tables": ("T_SVM_INQUIRYBILL", "T_SVM_INQUIRYBILLENTRY"),
    },

    "SVM_QuoteBill": {
        "name": "供应商报价单",
        "alias": ["报价单", "报价", "供应商报价", "报价响应"],
        "desc": "供应商对询价单的响应，包含物料价格、货期等信息。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FMaterialId.FName,FPrice,FQuantity,FDeliveryDate",
        "db_tables": ("T_SVM_QUOTEBILL", "T_SVM_QUOTEBILLENTRY"),
    },

    "SVM_ComparePrice": {
        "name": "比价单",
        "alias": ["比价", "比价单", "价格比较"],
        "desc": "对多个供应商报价进行比价分析，辅助采购决策。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FMaterialId.FName,FSupplierId.FName,FPrice,FBestSupplier",
        "db_tables": ("T_SVM_COMPAREPRICE",),
    },

    # ══════════════════════════════════════════════════════
    # 供应链：销售
    # ══════════════════════════════════════════════════════

    "SAL_SaleOrder": {
        "name": "销售订单",
        "alias": ["销售订单", "销售单", "SO", "销售合同"],
        "desc": (
            "企业与客户的销售协议，记录销售货物、价格、交货条件。"
            "可下推生成销售出库单、销售退货单、发货通知单等。"
        ),
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName,FSalesOrgId.FName,FSalesManId.FName,FTotalAmount,FLinkQty,FStockOutQty,FDeliQty",
        "db_tables": ("T_SAL_SALEORDER", "T_SAL_SALEORDERENTRY"),
        "business_rules": {
            "FLinkQty": "关联数量 = 已出库数量 + 已关联数量",
            "FStockOutQty": "累计出库数量（销售出库单审核时累加）",
            "FDeliQty": "累计发货数量",
            "关闭条件": "累计出库数量 >= 订单数量时自动行关闭",
            "冻结/终止": "冻结或终止的分录行不允许编辑和关联操作",
        },
    },

    "SAL_OUTSTOCK": {
        "name": "销售出库单",
        "alias": ["销售出库", "出货单", "发货单", "销售发货"],
        "desc": (
            "销售订单下推或手工创建的发货单据，确认货物出库并更新库存。"
            "审核时自动更新销售订单的累计出库数量。"
        ),
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName,FStockOrgId.FName,FStockId.FName,FOutQty",
        "db_tables": ("T_SAL_OUTSTOCK", "T_SAL_OUTSTOCKENTRY"),
        "business_rules": {
            "审核更新": "审核时累加销售订单【累计出库数量】；反审核时扣减",
            "可发量控制": "可发量不足时无法出库（勾选控制可发量时）",
        },
    },

    "SAL_RETURNSTOCK": {
        "name": "销售退货单",
        "alias": ["销售退货", "退货", "客户退货"],
        "desc": "客户因质量问题等原因退货的单据，审核时更新原销售订单的退货数量。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName,FReturnReason,FReturnQty",
        "db_tables": ("T_SAL_RETURNSTOCK", "T_SAL_RETURNSTOCKENTRY"),
    },

    "SAL_Quotation": {
        "name": "销售报价单",
        "alias": ["销售报价", "报价单", "SQ", "销售提案"],
        "desc": "向客户提供的商品或服务价格方案，可作为销售订单的参考价格。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName,FSalesmanId.FName,FTotalAmount,FExpiryDate",
        "db_tables": ("T_SAL_QUOTATION", "T_SAL_QUOTATIONENTRY"),
    },

    "SAL_DELIVERYNOTICE": {
        "name": "发货通知单",
        "alias": ["发货通知", "送货通知", "发货单"],
        "desc": "销售出库前的发货准备单据，可下推生成销售出库单。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName,FDeliveryDate,FNoticeQty",
        "db_tables": ("T_SAL_DELIVERYNOTICE", "T_SAL_DELIVERYNOTICEENTRY"),
    },

    "SAL_RetuenNotice": {
        "name": "退货通知单",
        "alias": ["退货通知", "退货单", "客户退货通知"],
        "desc": "客户退货时的通知单，可下推生成销售退货单。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName,FReturnReason,FReturnQty",
        "db_tables": ("T_SAL_RETURNNOTICE", "T_SAL_RETURNNOTICEENTRY"),
    },

    "SAL_AvailableQuery": {
        "name": "可发量查询",
        "alias": ["可发量", "可用量", "可用库存", "库存可用量"],
        "desc": "查询物料在指定仓库的可用库存数量（可发量 = 即时库存 - 已分配量）。",
        "fields": "FMaterialId.FNumber,FMaterialId.FName,FStockId.FName,FAvailableQty,FUnitId.FName",
        "db_tables": ("V_SAL_AVAILABLEQTY",),
    },

    # ══════════════════════════════════════════════════════
    # 供应链：库存
    # ══════════════════════════════════════════════════════

    "STK_InStock": {
        "name": "采购入库单",
        "alias": ["采购入库", "入库单", "入库", "来货入库"],
        "desc": (
            "物料实际验收入库的单据。来料检验的物料须先收料检验，合格后再入库；"
            "不需检验的物料可直接从采购订单下推入库。"
            "审核时累加采购订单【累计入库数量】。"
        ),
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FStockOrgId.FName,FStockId.FName,FMaterialId.FName,FInQty,FSupplierId.FName",
        "db_tables": ("T_STK_INSTOCK", "T_STK_INSTOCKENTRY"),
        "business_rules": {
            "审核更新": "入库单审核时累加采购订单【累计入库数量】；反审核时扣减",
            "交货数量控制": "勾选控制交货数量时，入库数量不能超过采购订单【交货上限】",
            "交货时间控制": "入库日期须在采购订单【最早/最晚交货时间】之间",
        },
    },

    "STK_MisDelivery": {
        "name": "其他出库单",
        "alias": ["其他出库", "杂发", "领料", "生产领料"],
        "desc": "除销售出库外的物料出库单据，如生产领料、样品领用等。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FStockOrgId.FName,FStockId.FName,FOutQty,FReason",
        "db_tables": ("T_STK_MISDELIVERY", "T_STK_MISDELIVERYENTRY"),
    },

    "STK_Miscellaneous": {
        "name": "其他入库单",
        "alias": ["其他入库", "杂收", "盘盈入库"],
        "desc": "除采购入库外的物料入库单据，如盘盈入库、样品入库等。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FStockOrgId.FName,FStockId.FName,FInQty,FReason",
        "db_tables": ("T_STK_MISCELLANEOUS", "T_STK_MISCELLANEOUSENTRY"),
    },

    "STK_TransferDirect": {
        "name": "直接调拨单",
        "alias": ["调拨", "调拨单", "库存调拨", "仓库调拨"],
        "desc": "仓库之间的物料调拨，单据审核后直接更新即时库存。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FStockOutId.FName,FStockInId.FName,FMaterialId.FName,FTransferQty",
        "db_tables": ("T_STK_TRANSFERDIRECT", "T_STK_TRANSFERDIRECTENTRY"),
    },

    "STK_Inventory": {
        "name": "即时库存",
        "alias": ["库存", "即时库存", "库存查询", "现存量"],
        "desc": "物料在各仓库的实时库存数量，是出入库业务的结果。",
        "fields": "FMaterialId.FNumber,FMaterialId.FName,FStockId.FName,FStockLocId.FName,FBaseQty,FUnitId.FName",
        "db_tables": ("T_STK_INVENTORY",),
        "business_rules": {
            "库存冻结": "冻结的库存行不允许出库",
            "批次管理": "有批号的物料出库须指定批号",
        },
    },

    "STK_StockCountInput": {
        "name": "盘点单",
        "alias": ["盘点", "盘点单", "库存盘点", "盘点"],
        "desc": "定期或不定期对仓库物料进行清点，差异生成其他出入库单据。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FStockId.FName,FInspectorId.FName,FStockTakeStatus",
        "db_tables": ("T_STK_STKCOUNTINPUT", "T_STK_STKCOUNTINPUTENTRY"),
    },

    "STK_TransferApply": {
        "name": "调拨申请单",
        "alias": ["调拨申请", "调拨单申请"],
        "desc": "申请仓库之间物料调拨，审核后下推生成调拨单。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FSendStockId.FName,FReceiveStockId.FName,FMaterialId.FName,FApplyQty",
        "db_tables": ("T_STK_TRANSFERAPPLY", "T_STK_TRANSFERAPPLYENTRY"),
    },

    "STK_TRANSFERIN": {
        "name": "分布式调入单",
        "alias": ["调入单", "调拨入库", "调拨接收"],
        "desc": "分布式调拨模式下的调入单，由调出单下推生成。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FStockOrgId.FName,FStockId.FName,FInQty",
        "db_tables": ("T_STK_TRANSFERIN", "T_STK_TRANSFERINENTRY"),
    },

    "STK_TRANSFEROUT": {
        "name": "分布式调出单",
        "alias": ["调出单", "调拨出库", "调拨发出"],
        "desc": "分布式调拨模式下的调出单，审核后下推生成调入单。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FStockOrgId.FName,FStockId.FName,FOutQty",
        "db_tables": ("T_STK_TRANSFEROUT", "T_STK_TRANSFEROUTENTRY"),
    },

    "STK_AssembledApp": {
        "name": "组装拆卸单",
        "alias": ["组装", "拆卸", "组装拆卸", "拆装"],
        "desc": "将多个物料组装为产成品，或将产成品拆卸为原材料。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FStockId.FName,FAssembleType,FMaterialId.FName",
        "db_tables": ("T_STK_ASSEMBLEAPP", "T_STK_ASSEMBLEAPPENTRY"),
    },

    "STK_OutStockApply": {
        "name": "出库申请单",
        "alias": ["出库申请", "领料申请"],
        "desc": "物料需要出库时发起的申请，如生产领料申请。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FStockOrgId.FName,FMaterialId.FName,FApplyQty",
        "db_tables": ("T_STK_OUTSTOCKAPPLY", "T_STK_OUTSTOCKAPPLYENTRY"),
    },

    "STK_StatusConvert": {
        "name": "形态转换单",
        "alias": ["形态转换", "库存状态", "状态转换"],
        "desc": "物料在仓库内的状态变更（如合格品→不良品），仅更新库存状态不移动数量。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FStockId.FName,FMaterialId.FName,FStatusBefore,FStatusAfter,FConvertQty",
        "db_tables": ("T_STK_STATUSCONVERT", "T_STK_STATUSCONVERTENTRY"),
    },

    # ══════════════════════════════════════════════════════
    # 供应链：质量
    # ══════════════════════════════════════════════════════

    "QIS_InspectBill": {
        "name": "来料检验单",
        "alias": ["来料检验", "质检单", "质量检验", "IQC", "来料质检"],
        "desc": (
            "对采购物料进行质量检验，判断是否允许入库。"
            "来料检验单须关联收料通知单生成；检验结果决定物料入合格品还是不良品库。"
        ),
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FMaterialId.FName,FPassQty,FFailQty,FInspectResult",
        "db_tables": ("T_QIS_INSPECTBILL", "T_QIS_INSPECTBILLENTRY"),
        "business_rules": {
            "检验结果": "FPassQty=合格数量，FFailQty=不合格数量",
            "合格品入库": "合格物料下推入库单至合格品仓库",
            "不合格处理": "不合格物料需走特采或退货流程",
        },
    },

    # ══════════════════════════════════════════════════════
    # 财务
    # ══════════════════════════════════════════════════════

    "AP_Payable": {
        "name": "应付单",
        "alias": ["应付", "应付单", "应付账款", "采购发票"],
        "desc": "记录企业对供应商的应付账款，由采购入库单下推或手工创建。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FAmount,FCloseStatus",
        "db_tables": ("T_AP_PAYABLE", "T_AP_PAYABLEENTRY"),
        "business_rules": {
            "核销": "付款单核销后，采购订单的预付金额会被占用",
            "付款关联": "采购订单被付款单关联后，不可反审核",
        },
    },

    "AR_Receivable": {
        "name": "应收单",
        "alias": ["应收", "应收单", "应收账款", "销售发票"],
        "desc": "记录企业应收客户的款项，由销售出库单下推或手工创建。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName,FAmount,FCloseStatus",
        "db_tables": ("T_AR_RECEIVABLE", "T_AR_RECEIVABLEENTRY"),
    },

    # ══════════════════════════════════════════════════════
    # 生产
    # ══════════════════════════════════════════════════════

    "PRD_MO": {
        "name": "生产订单",
        "alias": ["生产订单", "生产单", "MO", "工单", "工单生产"],
        "desc": (
            "生产部门依据生产计划下达的生产任务单，关联物料清单（BOM）和工艺路线。"
            "可下推生成生产领料单、产品入库单。"
        ),
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FMaterialId.FName,FUnitId.FName,FQty,FStockInQty,FPickMtrlQty,FPlanStartDate,FPlanFinishDate",
        "db_tables": ("T_PRD_MO", "T_PRD_MOENTRY"),
        "business_rules": {
            "FStockInQty": "累计产品入库数量（产品入库单审核时累加）",
            "FPickMtrlQty": "累计领料数量（生产领料单审核时累加）",
            "汇报投料": "生产汇报时投料数量累加至【累计投料数量】",
        },
    },

    "PRD_PickMtrl": {
        "name": "生产领料单",
        "alias": ["生产领料", "领料单", "领料"],
        "desc": "依据生产订单或工序汇报发起的领料单据，审核时扣减即时库存。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FMaterialId.FName,FStockId.FName,FPickQty,FMoBillNo",
        "db_tables": ("T_PRD_PICKMTRL", "T_PRD_PICKMTRLENTRY"),
        "business_rules": {
            "审核扣库": "审核时扣减即时库存；反审核时回补库存",
            "超领控制": "超领须经审批后才能继续领料",
        },
    },

    "PRD_Instock": {
        "name": "产品入库单",
        "alias": ["产品入库", "完工入库", "生产入库"],
        "desc": "生产完工的产品入库单据，审核时增加即时库存并更新生产订单。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FMaterialId.FName,FStockId.FName,FInQty,FMoBillNo",
        "db_tables": ("T_PRD_INSTOCK", "T_PRD_INSTOCKENTRY"),
    },

    # ══════════════════════════════════════════════════════
    # 费用报销
    # ══════════════════════════════════════════════════════

    "ER_ExpenseRequest": {
        "name": "费用申请单",
        "alias": ["费用申请", "申请单", "事前申请"],
        "desc": "业务发生前的事前费用申请，审核后可作为报销的依据。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FApplicantId.FName,FRequestDeptId.FName,FTotalAmount,FExpenseTypeId.FName",
        "db_tables": ("T_ER_EXPENSEREQUEST", "T_ER_EXPENSEREQUESTENTRY"),
    },

    "ER_ExpenseReimburse": {
        "name": "费用报销单",
        "alias": ["费用报销", "报销单", "报销", "事后报销"],
        "desc": "业务发生后的费用报销单据，可关联费用申请单，审核后生成付款单。",
        "fields": "FID,FBillNo,FDate,FDocumentStatus,FApplicantId.FName,FRequestDeptId.FName,FTotalReimAmount,FExpenseTypeId.FName",
        "db_tables": ("T_ER_EXPENSEREIMBURSE", "T_ER_EXPENSEREIMBURSEENTRY"),
        "business_rules": {
            "关联申请": "可关联费用申请单；无申请单的报销须走预算外审批流程",
            "审核后付款": "审核后可下推生成付款单",
        },
    },
}


# ─────────────────────────────────────────────
# 通用工具函数
# ─────────────────────────────────────────────

def _url(ep_key: str) -> str:
    return SERVER_URL.rstrip("/") + "/" + _EP[ep_key]


async def _login() -> str:
    """登录金蝶，返回 SessionId，失败抛异常"""
    global _session_id
    payload = {"parameters": [ACCT_ID, USERNAME, APP_ID, APP_SEC, LCID]}
    # 💡 REMEMBER: httpx 0.28+ 默认 HTTP/2，金蝶不支持，必须显式传 http1=True，否则全 502
    async with httpx.AsyncClient(timeout=30, proxy=None,
                                  transport=httpx.AsyncHTTPTransport(http1=True)) as client:
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
    """带自动重新登录的 API 调用（用于 Query 等只读操作）"""
    global _session_id

    # Query 的 payload 已是 dict（由 _query_payload 返回）
    # 其他操作的 payload 是 list：[formId, {params}]，需要合并
    if isinstance(payload, list) and len(payload) == 2:
        form_id, params = payload
        request_data = {"FormId": form_id, **params}
    else:
        request_data = payload

    async def _do_post(session: str) -> httpx.Response:
        # 所有 API 都用 form-urlencoded + JSON string 格式
        return await client.post(
            _url(ep_key),
            data={"data": json.dumps(request_data, ensure_ascii=False)},
            headers={
                "Cookie": f"kdservice-sessionid={session}",
            },
        )

    async with httpx.AsyncClient(timeout=30, proxy=None,
                                  transport=httpx.AsyncHTTPTransport(http1=True)) as client:
        # 没有 session 先登录
        if not _session_id:
            await _login()

        resp = await _do_post(_session_id)

        # session 过期则重新登录重试一次
        if resp.status_code == 401 or (
            resp.status_code == 200 and
            ("会话" in resp.text or "session" in resp.text.lower())
        ):
            await _login()
            resp = await _do_post(_session_id)

        resp.raise_for_status()
        return resp.json()


async def _post_raw(ep_key: str, form_id: str, model: dict,
                     need_update_fields: Optional[List[str]] = None,
                     need_return_fields: Optional[List[str]] = None,
                     is_delete_entry: bool = True) -> Any:
    """带自动重新登录的 raw JSON 调用（用于 Save/View/Submit/Audit/Push 等写操作）

    Kingdee WebAPI 写接口使用小写 formid + 嵌套 data 对象格式。
    - Save/View/Submit/Audit/Delete: data={"Model": {...}, NeedUpDateFields:[], ...}
    - Push: data={"TargetFormId":"...","Numbers":[...],"RuleId":"..."}  （无 Model 包装）
    """
    global _session_id

    # Push: data 直接放字段，不需要 Model 包装
    # Submit/Audit/Unaudiot/Delete: data 里面直接是 {"Ids": ...}，不需要 Model 包装
    # View: data 里面直接是 {"Id": ...}，不需要 Model 包装
    # Save: 需要 Model 包装
    # 注意：Kingdee WebAPI 中 data 字段始终是 JSON 字符串，不是对象
    if ep_key in ("push", "submit", "audit", "unaudit", "delete", "view"):
        data_obj = dict(model)
        # 💡 REMEMBER: Submit/Audit/Unaudiot/Delete 的 Ids 必须是单个字符串 {"Ids":"100"}，不是数组
        # Submit/Audit/Unaudiot/Delete: Ids 必须是单个字符串（FID），不是数组
        if ep_key in ("submit", "audit", "unaudit", "delete") and "Ids" in data_obj:
            ids = data_obj["Ids"]
            data_obj["Ids"] = ids[0] if isinstance(ids, (list, tuple)) else ids
    else:
        data_obj = {"Model": model}
        if need_update_fields:
            data_obj["NeedUpDateFields"] = need_update_fields
        if need_return_fields:
            data_obj["NeedReturnFields"] = need_return_fields
        if ep_key == "save":
            data_obj["IsDeleteEntry"] = "true" if is_delete_entry else "false"
            data_obj["IsVerifyBaseDataField"] = "false"
            data_obj["IsAutoSubmitAndAudit"] = "false"
            data_obj["ValidateRepeatJson"] = "false"

    # Kingdee WebAPI 格式（raw JSON body）：
    #   {"formid": "...", "data": "{\"Model\":{...}}"}
    # 💡 REMEMBER: data 字段是 JSON 字符串，只需一次 json.dumps；双重 dumps 会导致 API 报 502 或参数错误
    # Kingdee WebAPI 格式（raw JSON body）：{"formid": "...", "data": "{\"Model\":{...}}"}
    body_str = json.dumps({"formid": form_id, "data": json.dumps(data_obj, ensure_ascii=False)}, ensure_ascii=False)

    async with httpx.AsyncClient(timeout=30, proxy=None,
                                  transport=httpx.AsyncHTTPTransport(http1=True)) as client:
        if not _session_id:
            await _login()

        resp = await client.post(
            _url(ep_key),
            content=body_str.encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Cookie": f"kdservice-sessionid={_session_id}",
            },
        )

        if resp.status_code == 401 or (
            resp.status_code == 200 and
            ("会话" in resp.text or "session" in resp.text.lower())
        ):
            await _login()
            resp = await client.post(
                _url(ep_key),
                content=body_str.encode("utf-8"),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Cookie": f"kdservice-sessionid={_session_id}",
                },
            )

        resp.raise_for_status()
        return resp.json()


def _rows(result: Any) -> list:
    """从 API 返回中提取数据行"""
    if isinstance(result, list):
        return result
    return result.get("Result", result.get("data", []))


def _fmt(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# SQL Server 探查工具（可选功能）
# ─────────────────────────────────────────────

def _sql_connect():
    """建立 SQL Server 连接"""
    try:
        import pyodbc
    except ImportError:
        raise RuntimeError(
            "pyodbc 未安装，请运行：pip install pyodbc\n"
            "SQL Server 探查功能需要 pyodbc 驱动。"
        )
    if not _SQL_ENABLED:
        raise RuntimeError(
            "SQL Server 未配置。请设置以下环境变量：\n"
            "MCP_SQLSERVER_HOST / MCP_SQLSERVER_USER / MCP_SQLSERVER_PASSWORD / MCP_SQLSERVER_DATABASE"
        )
    driver = os.getenv("MCP_SQLSERVER_DRIVER", "ODBC Driver 17 for SQL Server")
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={_SQL_HOST},{_SQL_PORT};"
        f"DATABASE={_SQL_DATABASE};"
        f"UID={_SQL_USER};PWD={_SQL_PASSWORD};"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, timeout=10)


def _sql_rows(conn, query: str) -> List[dict]:
    """执行只读查询，返回行列表（字典格式）"""
    cursor = conn.cursor()
    cursor.execute(query)
    columns = [col[0] for col in cursor.description]
    rows = []
    for row in cursor.fetchall():
        rows.append(dict(zip(columns, row)))
    cursor.close()
    return rows


# ─────────────────────────────────────────────
# SQL Server 探查工具模型
# ─────────────────────────────────────────────

class SqlSearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    pattern: str = Field(default="", description="搜索关键字（表名/列名），支持模糊匹配，如 'purchase'、'supplier'")
    limit: int = Field(default=20, ge=1, le=200, description="最大返回条数")


class SqlDescribeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    table_name: str = Field(..., description="表名（不含 Schema 前缀），如 't_PUR_PurchaseOrder'")


class MetadataCandidateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(default="", description="金蝶 form_id，如 'PUR_PurchaseOrder'、'BD_Material'，留空则返回所有候选映射")
    limit: int = Field(default=20, ge=1, le=200, description="最大返回条数")


@mcp.tool(
    name="kingdee_discover_tables",
    annotations={"title": "搜索数据库表", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": True}
)
async def kingdee_discover_tables(params: SqlSearchInput) -> str:
    """搜索 SQL Server 中包含关键字的表名（仅查系统目录，不读业务数据）。

    适用场景：
    - 想知道"采购"相关的表有哪些
    - 快速定位业务表名，不记得确切名称时
    - 配合 kingdee_discover_columns 一起使用，先找表再看字段

    搜索范围：SQL Server 系统目录（information_schema.TABLES / sys.tables）

    Returns:
        str: 表名列表，含表名、类型、创建时间
    """
    if not params.pattern:
        return _fmt({
            "tip": "请提供搜索关键字，如 pattern='purchase' 或 pattern='供应商'"
        })

    try:
        conn = _sql_connect()
        try:
            rows = _sql_rows(conn, f"""
                SELECT TABLE_NAME, TABLE_TYPE
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = '{_SQL_SCHEMA}'
                  AND TABLE_TYPE = 'BASE TABLE'
                  AND (TABLE_NAME LIKE '%{params.pattern}%'
                       OR TABLE_NAME LIKE '%{params.pattern.upper()}%')
                ORDER BY TABLE_NAME
                OFFSET 0 ROWS FETCH NEXT {params.limit} ROWS ONLY
            """)
            return _fmt({
                "pattern": params.pattern,
                "schema": _SQL_SCHEMA,
                "database": _SQL_DATABASE,
                "count": len(rows),
                "tables": rows
            })
        finally:
            conn.close()
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_discover_columns",
    annotations={"title": "搜索数据库字段", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": True}
)
async def kingdee_discover_columns(params: SqlSearchInput) -> str:
    """按关键字搜索 SQL Server 中的列名（仅查系统目录，不读业务数据）。

    适用场景：
    - 想找一个"供应商编码"字段在哪些表里
    - 接口映射时，确认某个字段在数据库里的实际名称
    - 快速验证 Kingdee API 字段和数据库字段的对应关系

    Returns:
        str: 列名搜索结果，含表名、列名、数据类型、是否可空
    """
    if not params.pattern:
        return _fmt({
            "tip": "请提供搜索关键字，如 pattern='supplier' 或 pattern='金额'"
        })

    try:
        conn = _sql_connect()
        try:
            rows = _sql_rows(conn, f"""
                SELECT
                    c.TABLE_NAME,
                    c.COLUMN_NAME,
                    c.DATA_TYPE,
                    c.CHARACTER_MAXIMUM_LENGTH,
                    c.IS_NULLABLE,
                    c.COLUMN_DEFAULT,
                    c.ORDINAL_POSITION
                FROM INFORMATION_SCHEMA.COLUMNS c
                JOIN INFORMATION_SCHEMA.TABLES t
                  ON c.TABLE_SCHEMA = t.TABLE_SCHEMA
                 AND c.TABLE_NAME = t.TABLE_NAME
                 AND t.TABLE_TYPE = 'BASE TABLE'
                WHERE c.TABLE_SCHEMA = '{_SQL_SCHEMA}'
                  AND (c.COLUMN_NAME LIKE '%{params.pattern}%'
                       OR c.COLUMN_NAME LIKE '%{params.pattern.upper()}%')
                ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
                OFFSET 0 ROWS FETCH NEXT {params.limit} ROWS ONLY
            """)
            return _fmt({
                "pattern": params.pattern,
                "schema": _SQL_SCHEMA,
                "database": _SQL_DATABASE,
                "count": len(rows),
                "columns": rows
            })
        finally:
            conn.close()
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_describe_table",
    annotations={"title": "查看表结构", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": True}
)
async def kingdee_describe_table(params: SqlDescribeInput) -> str:
    """查看指定表的完整结构（列名、类型、可空、默认值）。

    适用场景：
    - 知道表名，想了解完整字段列表
    - 写 SQL 或做数据建模前，查看表结构
    - 确认 Kingdee API 返回的字段在数据库里的实际类型

    已知金蝶常用表名前缀：
    - t_PUR_：采购相关（t_PUR_PurchaseOrder 采购订单）
    - t_SAL_：销售相关（t_SAL_SaleOrder 销售订单）
    - t_STK_：库存相关（t_STK_InStock 入库单）
    - t_BD_：基础资料（t_BD_Material 物料、t_BD_Supplier 供应商）

    Returns:
        str: 表结构详情
    """
    try:
        conn = _sql_connect()
        try:
            rows = _sql_rows(conn, f"""
                SELECT
                    c.COLUMN_NAME,
                    c.DATA_TYPE,
                    c.CHARACTER_MAXIMUM_LENGTH,
                    c.NUMERIC_PRECISION,
                    c.NUMERIC_SCALE,
                    c.IS_NULLABLE,
                    c.COLUMN_DEFAULT,
                    c.ORDINAL_POSITION,
                    pk.COLUMN_NAME AS IS_PRIMARY_KEY,
                    fk.REFERENCED_TABLE_NAME,
                    fk.REFERENCED_COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS c
                LEFT JOIN (
                    SELECT cu.TABLE_SCHEMA, cu.TABLE_NAME, cu.COLUMN_NAME
                    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                    JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE cu
                      ON tc.CONSTRAINT_NAME = cu.CONSTRAINT_NAME
                    WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                      AND cu.TABLE_SCHEMA = '{_SQL_SCHEMA}'
                ) pk ON pk.TABLE_SCHEMA = c.TABLE_SCHEMA
                   AND pk.TABLE_NAME = c.TABLE_NAME
                   AND pk.COLUMN_NAME = c.COLUMN_NAME
                LEFT JOIN (
                    SELECT
                        kcu.TABLE_SCHEMA, kcu.TABLE_NAME, kcu.COLUMN_NAME,
                        kcu2.TABLE_NAME AS REFERENCED_TABLE_NAME,
                        kcu2.COLUMN_NAME AS REFERENCED_COLUMN_NAME
                    FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
                    JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                      ON rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                    JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu2
                      ON rc.UNIQUE_CONSTRAINT_NAME = kcu2.CONSTRAINT_NAME
                    WHERE kcu.TABLE_SCHEMA = '{_SQL_SCHEMA}'
                ) fk ON fk.TABLE_SCHEMA = c.TABLE_SCHEMA
                   AND fk.TABLE_NAME = c.TABLE_NAME
                   AND fk.COLUMN_NAME = c.COLUMN_NAME
                WHERE c.TABLE_SCHEMA = '{_SQL_SCHEMA}'
                  AND c.TABLE_NAME = '{params.table_name}'
                ORDER BY c.ORDINAL_POSITION
            """)
            if not rows:
                return _fmt({"error": f"表 '{params.table_name}' 不存在或无权访问。"})

            return _fmt({
                "table": params.table_name,
                "schema": _SQL_SCHEMA,
                "database": _SQL_DATABASE,
                "count": len(rows),
                "columns": rows
            })
        finally:
            conn.close()
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_discover_metadata_candidates",
    annotations={"title": "金蝶元数据候选发现", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": True}
)
async def kingdee_discover_metadata_candidates(params: MetadataCandidateInput) -> str:
    """发现金蝶数据库中与指定 form_id 或 form_id 前缀对应的表。

    这是面向金蝶/K3 场景的辅助工具：根据 form_id 推测对应的数据库表名。

    form_id → 表名对应规律：
    - PUR_PurchaseOrder  → t_PUR_PurchaseOrder（采购订单）
    - SAL_SaleOrder     → t_SAL_SaleOrder（销售订单）
    - STK_InStock       → t_STK_InStock（入库单）
    - BD_Material       → t_BD_Material（物料）
    - BD_Supplier       → t_BD_Supplier（供应商）
    - BD_Customer       → t_BD_Customer（客户）

    适用场景：
    - 想知道某个 form_id 对应数据库里哪张表
    - 想探索某类单据的所有关联表（如采购全流程：订单→收料→入库）
    - 理解金蝶 form_id 和数据库表名的映射关系

    Returns:
        str: form_id 与表名的候选映射列表
    """
    # 从 FORM_CATALOG 中自动提取 form_id → (主表, [分录表]) 的映射
    candidates: list[tuple[str, str, str]] = []
    for fid, info in FORM_CATALOG.items():
        tables = info.get("db_tables", ())
        if tables:
            main_table = tables[0]
            name = info.get("name", fid)
            candidates.append((fid, main_table, name))

    try:
        conn = _sql_connect()
        try:
            # 按 form_id 过滤（如指定了）
            if params.form_id:
                filtered: list[tuple[str, str, str]] = [
                    (fid, tbl, name) for fid, tbl, name in candidates
                    if params.form_id.lower() in fid.lower()
                ]
            else:
                filtered = candidates

            filtered = filtered[:params.limit]

            # 检查哪些表真实存在（同时查询主表和分录表）
            results = []
            for form_id, table_name, description in filtered:
                rows = _sql_rows(conn, f"""
                    SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA = '{_SQL_SCHEMA}'
                      AND TABLE_NAME = '{table_name}'
                      AND TABLE_TYPE = 'BASE TABLE'
                """)
                # 同时列出该表单的所有关联表
                info = FORM_CATALOG.get(form_id, {})
                all_tables = info.get("db_tables", ())
                table_exists = {t: False for t in all_tables}
                if rows:
                    table_exists[table_name] = True
                # 查询分录表
                for t in all_tables[1:]:
                    r = _sql_rows(conn, f"""
                        SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                        WHERE TABLE_SCHEMA = '{_SQL_SCHEMA}'
                          AND TABLE_NAME = '{t}'
                          AND TABLE_TYPE = 'BASE TABLE'
                    """)
                    if r:
                        table_exists[t] = True
                exists_list = [t for t, e in table_exists.items() if e]
                results.append({
                    "form_id": form_id,
                    "table_name": table_name,
                    "description": description,
                    "exists": len(rows) > 0,
                    "db_tables": all_tables,
                    "exists_tables": exists_list,
                    "has_all_tables": set(exists_list) == set(all_tables),
                    "suggestion": (
                        f"调用 kingdee_describe_table(table_name='{table_name}') 查看表结构"
                        if rows else f"表 '{table_name}' 不存在，可能使用不同命名规则"
                    ),
                })

            return _fmt({
                "form_id_filter": params.form_id or "(全部)",
                "schema": _SQL_SCHEMA,
                "database": _SQL_DATABASE,
                "count": len(results),
                "tip": "exists_tables=数据库中存在的表；has_all_tables=true 表示主表和分录表均存在",
                "results": results
            })
        finally:
            conn.close()
    except Exception as e:
        return _err(e)


def _query_payload(form_id: str, field_keys: str, filter_string: str,
                   order_string: str, start_row: int, limit: int) -> dict:
    """Query API 请求数据（dict 格式，_post 会直接作为 JSON body 发送）"""
    return {
        "FormId": form_id,
        "FieldKeys": field_keys,
        "FilterString": filter_string,
        "OrderString": order_string,
        "StartRow": start_row,
        "Limit": limit,
    }


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


class PurchaseOrderProgressInput(BaseModel):
    """采购订单行明细/执行进度查询的输入模型。"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    filter_string: str = Field(
        default="FDocumentStatus='C'",
        description="过滤条件，默认只查已审核单据，如 \"FSupplierId.FNumber='S001'\""
    )
    start_row: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


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
        # View 使用 _post_raw（raw JSON body + 小写 formid，无 Model 包装）
        result = await _post_raw("view", params.form_id, {"Id": params.bill_id})
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
    - 未关闭: "FCloseStatus='A'"
    - 业务正常: "FBusinessClose='A'"

    推荐 field_keys（默认已包含关键执行字段）：
    FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FPurchaseDeptId.FName,
    FTaxAmount,FAllAmount,FReceiveQty,FStockInQty

    注：FTotalAmount/FLinkQty/FBusinessClose 等字段在 demo 环境可能不存在，
    如需关联数量，请用 FReceiveQty + FStockInQty 代替，或用 kingdee_get_fields 确认可用字段

    关联数量业务规则：
    - 关联数量 = 累计收料数量 + 累计入库数量
    - 关联数量 >= 订单数量时，采购订单无法下推收料单/入库单
    - 勾选控制交货数量时，关联数量 >= 交货下限时无法下推

    Returns:
        str: JSON 格式的采购订单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else (
                "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,"
                "FPurchaseDeptId.FName,FTaxAmount,FAllAmount,"
                "FReceiveQty,FStockInQty"
                # FLinkQty/FBusinessClose 在 demo 环境可能不存在，请用 kingdee_get_fields 确认
            )
        result = await _post("query", _query_payload(
            "PUR_PurchaseOrder", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_purchase_order_progress",
    annotations={"title": "查询采购订单执行进度", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_purchase_order_progress(params: PurchaseOrderProgressInput) -> str:
    """查询采购订单行明细及执行进度（含累计收料/入库数量）。

    与 kingdee_query_purchase_orders 的区别：
    - 本工具查询【表体分录级】字段，返回每行物料的详细执行情况
    - 默认返回已审核单据，可通过 filter_string 过滤

    返回的关键字段（demo 账套实测）：
    - FBillNo: 单据编号
    - FMaterialId.FNumber / FMaterialId.FName: 物料编码/名称
    - FQty: 订单数量
    - FReceiveQty: 累计收料数量
    - FStockInQty: 累计入库数量
    - FPrice: 单价（不含税）
    - FTaxPrice: 含税单价
    - FAllAmount: 价税合计

    以下字段需启用供应链模块后才存在（demo 环境可能不存在）：
    - FLinkQty: 关联数量（=累计收料数量+累计入库数量）
    - FBusinessClose: 业务关闭状态（A=正常，B=业务关闭）
    - FFreezeStatus: 冻结状态（A=正常，B=冻结）
    - FTerminateStatus: 终止状态（A=正常，B=终止）
    - FDlyCntl_Low / FDlyCntl_High: 交货下限/上限

    业务关闭规则（需启用供应链）：
    - 累计入库数量 >= 交货下限时，该行自动【业务关闭】
    - 累计入库数量 < 交货下限时，自动【业务反关闭】

    Returns:
        str: JSON 格式的采购订单执行进度列表
    """
    try:
        # 注：FLinkQty/FBusinessClose/FFreezeStatus/FTerminateStatus/FDlyCntl_* 在 demo 环境可能不存在
        # 如遇字段不存在错误，请用 kingdee_get_fields(form_id='PUR_PurchaseOrder') 确认
        field_keys = (
            "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,"
            "FMaterialId.FNumber,FMaterialId.FName,"
            "FQty,FReceiveQty,FStockInQty,"
            "FPrice,FTaxPrice,FAllAmount"
        )
        result = await _post("query", _query_payload(
            "PUR_PurchaseOrder", field_keys,
            params.filter_string or "FDocumentStatus='C'",
            "FBillNo DESC,FPOOrderEntry_LineID ASC",
            params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({
            "tip": (
                "FLinkQty=关联数量（=FReceiveQty+FStockInQty），"
                "FLinkQty>=FQty时无法下推；"
                "累计入库数量>=交货下限时该行自动业务关闭"
            ),
            "count": len(rows),
            "has_more": len(rows) == params.limit,
            "data": rows
        })
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
        # 构建 Kingdee Save API 格式：
        # data 内部 Model（单据字段）和 NeedUpDateFields 等是同级兄弟节点
        model = dict(params.model)
        # 新建时 FID 设为 0，修改时保留原 FID
        model.setdefault("FID", 0)

        result = await _post_raw(
            "save",
            params.form_id,
            model,
            need_update_fields=params.need_update_fields,
            need_return_fields=["FID", "FBillNo"],
            is_delete_entry=params.is_delete_entry,
        )

        # 提取新建单据的 FID 和 FBillNo，使用结构化结果
        status_data = _result_status(result, "save")
        if status_data.get("success"):
            status_data["tip"] = "单据已保存为草稿，需要提交+审核后才能生效"
        return _fmt(status_data)
    except Exception as e:
        return _err(e, op="save")


@mcp.tool(
    name="kingdee_submit_bills",
    annotations={"title": "提交单据", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_submit_bills(params: BillIdsInput) -> str:
    """提交单据（草稿 → 待审核）。

    返回结构化结果：success=true 时包含 next_action 字段，建议调用 kingdee_audit_bills 完成审核。

    Returns:
        str: JSON，含 success / next_action / bill_ids 字段
    """
    try:
        result = await _post_raw("submit", params.form_id, {"Ids": params.bill_ids})
        status_data = _result_status(result, "submit")
        if status_data.get("success"):
            status_data["bill_ids"] = params.bill_ids
            status_data["tip"] = "单据已提交，请在审核通过后调用 kingdee_audit_bills 审核"
        return _fmt(status_data)
    except Exception as e:
        return _err(e, op="submit")


@mcp.tool(
    name="kingdee_audit_bills",
    annotations={"title": "审核单据", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_audit_bills(params: BillIdsInput) -> str:
    """审核单据（待审核 → 已审核）。

    返回结构化结果：success=true 时表示单据已生效，next_action=null。

    Returns:
        str: JSON，含 success / bill_ids 字段
    """
    try:
        result = await _post_raw("audit", params.form_id, {"Ids": params.bill_ids})
        status_data = _result_status(result, "audit")
        if status_data.get("success"):
            status_data["bill_ids"] = params.bill_ids
            status_data["tip"] = "单据已审核生效。如需修改，请先调用 kingdee_unaudit_bills 反审核"
        return _fmt(status_data)
    except Exception as e:
        return _err(e, op="audit")


@mcp.tool(
    name="kingdee_unaudit_bills",
    annotations={"title": "反审核单据", "readOnlyHint": False, "destructiveHint": True,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_unaudit_bills(params: BillIdsInput) -> str:
    """反审核单据（已审核 → 待审核）。反审核后可重新修改和提交。

    返回结构化结果：success=true 时表示单据已回到待审核状态。

    Returns:
        str: JSON，含 success / bill_ids 字段
    """
    try:
        result = await _post_raw("unaudit", params.form_id, {"Ids": params.bill_ids})
        status_data = _result_status(result, "unaudit")
        if status_data.get("success"):
            status_data["bill_ids"] = params.bill_ids
            status_data["tip"] = "单据已反审核，可修改后重新提交+审核"
        return _fmt(status_data)
    except Exception as e:
        return _err(e, op="unaudit")


@mcp.tool(
    name="kingdee_delete_bills",
    annotations={"title": "删除单据", "readOnlyHint": False, "destructiveHint": True,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_delete_bills(params: BillIdsInput) -> str:
    """删除单据（仅草稿状态可删除，已提交/已审核的单据需先反审核）。

    返回结构化结果：success=true 时表示删除成功。

    Returns:
        str: JSON，含 success / bill_ids 字段
    """
    try:
        result = await _post_raw("delete", params.form_id, {"Ids": params.bill_ids})
        status_data = _result_status(result, "delete")
        if status_data.get("success"):
            status_data["bill_ids"] = params.bill_ids
            status_data["tip"] = "单据已删除。如需恢复，请重新创建"
        return _fmt(status_data)
    except Exception as e:
        return _err(e, op="delete")


class PushDownInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(..., description="源单据类型，如 SAL_SaleOrder、PUR_PurchaseOrder")
    target_form_id: str = Field(..., description="目标单据类型，如 SAL_OUTSTOCK、STK_InStock")
    source_bill_nos: List[str] = Field(
        ..., description="源单据编号列表（FBillNo），如 CGDD000025", min_length=1
    )
    rule_id: str = Field(
        default="",
        description="转换规则 ID（RuleId），如 PUR_PurchaseOrder-PUR_ReceiveBill。"
                    "未指定时由系统默认规则决定（下推失败时请尝试显式指定）"
    )
    enable_default_rule: bool = Field(
        default=False,
        description="是否启用默认转换规则。设为 true 时，Kingdee 自动使用该单据的默认下推规则，"
                    "无需手动指定 rule_id（生产环境常用）"
    )
    draft_on_fail: bool = Field(
        default=False,
        description="保存失败时是否暂存（非必填：暂存的单据没有单据编号）。"
                    "设为 true当下推后保存报错时，目标单据会转为暂存状态而非直接失败"
    )


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

    转换规则说明：
    - 默认（rule_id=空，enable_default_rule=false）：Kingdee 使用系统配置的默认转换规则
    - enable_default_rule=true：强制启用该单据的默认下推规则，忽略 rule_id
    - rule_id 显式指定：绕过默认规则，直接使用指定规则（下推失败时常用此方式）

    采购订单下推限制（关联数量规则）：
    - 采购订单【关联数量】>=【订单数量】时，无法下推收料单/入库单
      （关联数量 = 累计收料数量 + 累计入库数量）
    - 勾选【控制交货数量】时：
      - 关联数量 >= 交货下限时，无法下推
      - 关联数量 + 本次下推数量 > 交货上限时，目标单据无法保存
    - 单据状态必须为"已审核"，且未关闭、业务状态为"正常"

    响应包含：
    - Result.ResponseStatus：保存结果（IsSuccess 判断整体是否成功）
    - Result.ConvertResponseStatus：每行下推转换结果（可查看具体分录成功/失败）

    Returns:
        str: JSON，含 success / bill_nos / next_action 字段（成功时包含目标单据编号）
    """
    try:
        push_data: dict[str, Any] = {
            "TargetFormId": params.target_form_id,
            "Numbers": params.source_bill_nos,
        }
        if params.rule_id:
            push_data["RuleId"] = params.rule_id
        if params.enable_default_rule:
            push_data["IsEnableDefaultRule"] = "true"
        if params.draft_on_fail:
            push_data["IsDraftWhenSaveFail"] = "true"
        result = await _post_raw("push", params.form_id, push_data)
        status_data = _result_status(result, "push")
        # 提取生成的目标单据编号
        rs = result.get("Result", result) if isinstance(result, dict) else {}
        numbers = rs.get("Numbers", [])
        ids = rs.get("Ids", [])
        if status_data.get("success"):
            status_data["source_bill_nos"] = params.source_bill_nos
            status_data["target_form_id"] = params.target_form_id
            if numbers:
                status_data["target_bill_nos"] = numbers
            if ids:
                status_data["target_fids"] = ids if isinstance(ids, list) else [ids]
            status_data["tip"] = (
                f"已生成 {len(numbers)} 张目标单据，"
                "请依次调用 kingdee_submit_bills + kingdee_audit_bills 完成提交和审核"
            )
        return _fmt(status_data)
    except Exception as e:
        return _err(e, op="push")


# ─────────────────────────────────────────────
# 复合工作流工具（高层）：避免 AI 漏掉中间步骤导致的目标漂移
# ─────────────────────────────────────────────

class CreateAndAuditInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(..., description="单据类型，如 SAL_SaleOrder、PUR_PurchaseOrder")
    model: dict = Field(..., description="单据字段（同 kingdee_save_bill 的 model）")
    need_update_fields: List[str] = Field(default_factory=list, description="修改时需更新的字段名")
    is_delete_entry: bool = Field(default=True, description="保存时是否清空原分录")


class PushAndAuditInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(..., description="源单据类型，如 PUR_PurchaseOrder")
    target_form_id: str = Field(..., description="目标单据类型，如 STK_InStock")
    source_bill_nos: List[str] = Field(..., min_length=1, description="源单 FBillNo 列表")
    rule_id: str = Field(default="", description="转换规则 ID，demo 环境通常必填")
    enable_default_rule: bool = Field(default=False, description="启用默认下推规则（生产环境常用）")
    draft_on_fail: bool = Field(default=False, description="保存失败时目标单暂存（暂存的单无单据编号）")
    auto_submit_audit: bool = Field(
        default=True,
        description="为 false 时只下推不审核，目标单留为草稿。需要在 push 后做人工校验时关闭。",
    )


def _step_failed_status(result: Any, op: str) -> dict:
    """run a _post_raw 已返回 result 后，检查是否业务失败，构造步骤记录。"""
    return _result_status(result, op)


@mcp.tool(
    name="kingdee_create_and_audit",
    annotations={"title": "创建并审核单据（一站式）", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_create_and_audit(params: CreateAndAuditInput) -> str:
    """一次性走完 Save → Submit → Audit 三步，避免 AI 漏掉中间步骤。

    任意一步失败即停止（不自动重试），返回 halted_at 和 recovery_hint 告诉 AI
    从哪里手动接手。失败日志按整体 op="create_and_audit" 记录一次（不会三倍膨胀）。

    适用场景：明确要"一条龙"创建并使单据生效，没有中间审批/校验需求。
    需要中间步骤校验时，请改用手工链路 kingdee_save_bill → kingdee_submit_bills → kingdee_audit_bills。

    Returns:
        str: JSON。成功：success=true、halted_at=null、steps 三条均 success。
             失败：success=false、halted_at 指出卡点、recovery_hint 给出下一步建议。
    """
    steps: list[dict] = []
    out: dict[str, Any] = {"op": "create_and_audit", "success": False, "halted_at": None, "steps": steps}

    # Step 1: Save
    try:
        model = dict(params.model)
        model.setdefault("FID", 0)
        save_result = await _post_raw(
            "save",
            params.form_id,
            model,
            need_update_fields=params.need_update_fields,
            need_return_fields=["FID", "FBillNo"],
            is_delete_entry=params.is_delete_entry,
        )
    except Exception as e:
        steps.append({"op": "save", "success": False, "exception": f"{type(e).__name__}: {e}"})
        out["halted_at"] = "save"
        out["recovery_hint"] = "Save 抛异常未生成草稿，无需清理。修正 model 后重试 kingdee_create_and_audit 或调用 kingdee_save_bill。"
        return _err(e, extra_errors=[{"step": "save", "stage_summary": out}], op="create_and_audit")

    save_status = _result_status(save_result, "save")
    fid = save_status.get("fid")
    bill_no = save_status.get("bill_no")
    step_save = {"op": "save", "success": save_status.get("success", False)}
    if fid:
        step_save["fid"] = fid
        out["fid"] = fid
    if bill_no:
        step_save["bill_no"] = bill_no
        out["bill_no"] = bill_no
    if not save_status.get("success"):
        step_save["errors"] = save_status.get("errors", [])
        steps.append(step_save)
        out["halted_at"] = "save"
        out["errors"] = save_status.get("errors", [])
        out["recovery_hint"] = "Save 失败：检查 errors[].matched.suggestion；修正 model 后重试。"
        # 失败日志只在 composite 层记一次
        try:
            from scripts.failure_log import FailureLogger
            FailureLogger().log("create_and_audit", out)
        except Exception:
            pass
        return _fmt(out)
    steps.append(step_save)

    # Step 2: Submit
    try:
        submit_result = await _post_raw("submit", params.form_id, {"Ids": str(fid)})
    except Exception as e:
        steps.append({"op": "submit", "success": False, "exception": f"{type(e).__name__}: {e}"})
        out["halted_at"] = "submit"
        out["recovery_hint"] = (
            f"草稿已生成 (fid={fid}, bill_no={bill_no})。Submit 抛异常。"
            f"可手动调用 kingdee_submit_bills(form_id=\"{params.form_id}\", bill_ids=[\"{fid}\"]) 重试，"
            f"或先 kingdee_delete_bills 清理草稿。"
        )
        return _err(e, extra_errors=[{"step": "submit", "stage_summary": out}], op="create_and_audit")

    submit_status = _result_status(submit_result, "submit")
    step_submit = {"op": "submit", "success": submit_status.get("success", False)}
    if not submit_status.get("success"):
        step_submit["errors"] = submit_status.get("errors", [])
        steps.append(step_submit)
        out["halted_at"] = "submit"
        out["errors"] = submit_status.get("errors", [])
        out["recovery_hint"] = (
            f"草稿已生成 (fid={fid})。Submit 失败：检查 errors[].matched.suggestion。"
            f"修正后调用 kingdee_submit_bills(form_id=\"{params.form_id}\", bill_ids=[\"{fid}\"]) 重试。"
        )
        try:
            from scripts.failure_log import FailureLogger
            FailureLogger().log("create_and_audit", out)
        except Exception:
            pass
        return _fmt(out)
    steps.append(step_submit)

    # Step 3: Audit
    try:
        audit_result = await _post_raw("audit", params.form_id, {"Ids": str(fid)})
    except Exception as e:
        steps.append({"op": "audit", "success": False, "exception": f"{type(e).__name__}: {e}"})
        out["halted_at"] = "audit"
        out["recovery_hint"] = (
            f"已 Save+Submit (fid={fid})。Audit 抛异常。"
            f"可手动调用 kingdee_audit_bills(form_id=\"{params.form_id}\", bill_ids=[\"{fid}\"]) 重试。"
        )
        return _err(e, extra_errors=[{"step": "audit", "stage_summary": out}], op="create_and_audit")

    audit_status = _result_status(audit_result, "audit")
    step_audit = {"op": "audit", "success": audit_status.get("success", False)}
    if not audit_status.get("success"):
        step_audit["errors"] = audit_status.get("errors", [])
        steps.append(step_audit)
        out["halted_at"] = "audit"
        out["errors"] = audit_status.get("errors", [])
        out["recovery_hint"] = (
            f"已 Save+Submit (fid={fid})。Audit 失败（典型原因：必录字段未补、关联数据缺失）："
            f"检查 errors[].matched.suggestion；修正后调用 kingdee_audit_bills 重试。"
        )
        try:
            from scripts.failure_log import FailureLogger
            FailureLogger().log("create_and_audit", out)
        except Exception:
            pass
        return _fmt(out)
    steps.append(step_audit)

    out["success"] = True
    out["next_action"] = None
    out["tip"] = "工作流完成，单据已审核生效。如需修改，请先 kingdee_unaudit_bills 反审核。"
    return _fmt(out)


@mcp.tool(
    name="kingdee_push_and_audit",
    annotations={"title": "下推并审核目标单（一站式）", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_push_and_audit(params: PushAndAuditInput) -> str:
    """一次性走完 Push → (可选 Submit + Audit) 全流程。

    Push 生成的目标单默认是草稿；本工具自动批量提交+审核所有生成的目标单 FID。
    任何一步失败即停止；失败日志按整体 op="push_and_audit" 记录一次。

    auto_submit_audit=False 时退化为纯 push（与 kingdee_push_bill 等价，但返回 steps 结构）。

    Returns:
        str: JSON。含 steps、target_bill_nos、target_fids、halted_at / recovery_hint。
    """
    steps: list[dict] = []
    out: dict[str, Any] = {
        "op": "push_and_audit", "success": False, "halted_at": None, "steps": steps,
        "source_bill_nos": params.source_bill_nos, "target_form_id": params.target_form_id,
    }

    # Step 1: Push
    push_data: dict[str, Any] = {
        "TargetFormId": params.target_form_id,
        "Numbers": params.source_bill_nos,
    }
    if params.rule_id:
        push_data["RuleId"] = params.rule_id
    if params.enable_default_rule:
        push_data["IsEnableDefaultRule"] = "true"
    if params.draft_on_fail:
        push_data["IsDraftWhenSaveFail"] = "true"

    try:
        push_result = await _post_raw("push", params.form_id, push_data)
    except Exception as e:
        steps.append({"op": "push", "success": False, "exception": f"{type(e).__name__}: {e}"})
        out["halted_at"] = "push"
        out["recovery_hint"] = "Push 抛异常，未生成目标单。检查源单状态/转换规则/连通性后重试。"
        return _err(e, extra_errors=[{"step": "push", "stage_summary": out}], op="push_and_audit")

    push_status = _result_status(push_result, "push")
    rs = push_result.get("Result", push_result) if isinstance(push_result, dict) else {}
    target_bill_nos = rs.get("Numbers", []) or []
    target_fids_raw = rs.get("Ids", []) or []
    target_fids = [str(x) for x in (target_fids_raw if isinstance(target_fids_raw, list) else [target_fids_raw])]

    step_push: dict[str, Any] = {"op": "push", "success": push_status.get("success", False)}
    if target_bill_nos:
        step_push["target_bill_nos"] = target_bill_nos
        out["target_bill_nos"] = target_bill_nos
    if target_fids:
        step_push["target_fids"] = target_fids
        out["target_fids"] = target_fids
    if not push_status.get("success"):
        step_push["errors"] = push_status.get("errors", [])
        steps.append(step_push)
        out["halted_at"] = "push"
        out["errors"] = push_status.get("errors", [])
        out["recovery_hint"] = (
            "Push 失败：检查 errors[].matched.suggestion；常见原因——关联数量已达上限、"
            "转换规则不匹配、源单未审核。"
        )
        try:
            from scripts.failure_log import FailureLogger
            FailureLogger().log("push_and_audit", out)
        except Exception:
            pass
        return _fmt(out)
    steps.append(step_push)

    # 不需要后续 submit+audit
    if not params.auto_submit_audit:
        out["success"] = True
        out["tip"] = (
            f"已生成 {len(target_bill_nos)} 张目标草稿单。auto_submit_audit=False，"
            "请按需手动 kingdee_submit_bills + kingdee_audit_bills。"
        )
        out["next_action"] = "submit+audit"
        return _fmt(out)

    if not target_fids:
        out["halted_at"] = "submit"
        out["recovery_hint"] = "Push 成功但未返回目标 FID，无法自动 Submit。请用 target_bill_nos 反查 FID。"
        out["errors"] = [{"message": "Push response missing Ids"}]
        return _fmt(out)

    # Step 2: Submit (batch)
    try:
        submit_result = await _post_raw("submit", params.target_form_id, {"Ids": target_fids})
    except Exception as e:
        steps.append({"op": "submit", "success": False, "exception": f"{type(e).__name__}: {e}"})
        out["halted_at"] = "submit"
        out["recovery_hint"] = (
            f"已下推目标草稿 fids={target_fids}。Submit 抛异常。"
            f"手动 kingdee_submit_bills(form_id=\"{params.target_form_id}\", bill_ids={target_fids}) 重试。"
        )
        return _err(e, extra_errors=[{"step": "submit", "stage_summary": out}], op="push_and_audit")

    submit_status = _result_status(submit_result, "submit")
    step_submit = {"op": "submit", "success": submit_status.get("success", False)}
    if not submit_status.get("success"):
        step_submit["errors"] = submit_status.get("errors", [])
        steps.append(step_submit)
        out["halted_at"] = "submit"
        out["errors"] = submit_status.get("errors", [])
        out["recovery_hint"] = (
            f"目标草稿已生成 fids={target_fids}。Submit 失败：检查 errors[].matched.suggestion。"
        )
        try:
            from scripts.failure_log import FailureLogger
            FailureLogger().log("push_and_audit", out)
        except Exception:
            pass
        return _fmt(out)
    steps.append(step_submit)

    # Step 3: Audit (batch)
    try:
        audit_result = await _post_raw("audit", params.target_form_id, {"Ids": target_fids})
    except Exception as e:
        steps.append({"op": "audit", "success": False, "exception": f"{type(e).__name__}: {e}"})
        out["halted_at"] = "audit"
        out["recovery_hint"] = (
            f"已 Push+Submit 目标单 fids={target_fids}。Audit 抛异常。"
            f"手动 kingdee_audit_bills(form_id=\"{params.target_form_id}\", bill_ids={target_fids}) 重试。"
        )
        return _err(e, extra_errors=[{"step": "audit", "stage_summary": out}], op="push_and_audit")

    audit_status = _result_status(audit_result, "audit")
    step_audit = {"op": "audit", "success": audit_status.get("success", False)}
    if not audit_status.get("success"):
        step_audit["errors"] = audit_status.get("errors", [])
        steps.append(step_audit)
        out["halted_at"] = "audit"
        out["errors"] = audit_status.get("errors", [])
        out["recovery_hint"] = (
            f"已 Push+Submit 目标单 fids={target_fids}。Audit 失败：检查 errors[].matched.suggestion；"
            f"修正后调用 kingdee_audit_bills 重试。"
        )
        try:
            from scripts.failure_log import FailureLogger
            FailureLogger().log("push_and_audit", out)
        except Exception:
            pass
        return _fmt(out)
    steps.append(step_audit)

    out["success"] = True
    out["next_action"] = None
    out["tip"] = (
        f"工作流完成：已下推并审核 {len(target_fids)} 张目标单 ({params.target_form_id})。"
    )
    return _fmt(out)


# ─────────────────────────────────────────────
# 系统设置工具：用户/角色/权限/编码规则/系统配置查询
# ─────────────────────────────────────────────

class UserQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    filter_string: str = Field(default="", description="过滤条件，如 \"FUserID.FNumber='admin'\"")
    field_keys: str = Field(default="FUserID,FName,FNumber,FDepartment.FName,FIsActive", description="返回字段")
    start_row: int = Field(default=0, ge=0, description="分页起始行")
    limit: int = Field(default=20, ge=1, le=100, description="每页条数")


class RoleQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    filter_string: str = Field(default="", description="过滤条件")
    field_keys: str = Field(default="FRoleID,FName,FNumber,FIsActive", description="返回字段")
    start_row: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class PermissionQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    filter_string: str = Field(default="", description="过滤条件，如 \"FRoleId.FNumber='ROLE001'\"")
    field_keys: str = Field(default="FPermissionId,FName,FNumber,FObjectType", description="返回字段")
    start_row: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class SequenceQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    filter_string: str = Field(default="", description="过滤条件")
    field_keys: str = Field(default="FSequenceRuleId,FName,FNumber,FObjectType,FDescription", description="返回字段")
    start_row: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class NumberRuleQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    filter_string: str = Field(default="", description="过滤条件，如 \"FObjectType='SAL_SaleOrder'\"")
    field_keys: str = Field(default="FNumberRuleId,FName,FNumber,FObjectType,FPrefix,FSequenceLength", description="返回字段")
    start_row: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class SystemConfigInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    filter_string: str = Field(default="", description="过滤条件，如 \"FConfigKey='MaxUploadSize'\"")
    field_keys: str = Field(default="FConfigId,FConfigKey,FConfigValue,FDescription,FCategory", description="返回字段")
    start_row: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


def _system_query_payload(form_id: str, field_keys: str, filter_string: str, start_row: int, limit: int) -> list:
    return [form_id, {"FieldKeys": field_keys, "FilterString": filter_string, "StartRow": start_row, "Limit": limit}]


def _post_system(ep_key: str, form_id: str, field_keys: str, filter_string: str, start_row: int, limit: int) -> Any:
    return _post(ep_key, _system_query_payload(form_id, field_keys, filter_string, start_row, limit))


@mcp.tool(
    name="kingdee_query_user",
    annotations={"title": "查询用户", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_user(params: UserQueryInput) -> str:
    """查询金蝶系统中的用户列表。

    常用 filter_string：
    - 指定用户名: "FUserID.FNumber='user001'"
    - 在岗状态: "FIsActive=1"
    - 指定部门: "FDepartment.FNumber='D001'"

    推荐 field_keys：
    FUserID,FName,FNumber,FDepartment.FName,FIsActive,FCreateDate

    Returns:
        str: JSON 格式的用户列表
    """
    try:
        result = await _post_system("user", "BD_User", params.field_keys, params.filter_string, params.start_row, params.limit)
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_role",
    annotations={"title": "查询角色", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_role(params: RoleQueryInput) -> str:
    """查询金蝶系统中的角色列表。

    常用 filter_string：
    - 指定角色名: "FRoleID.FNumber='admin'"
    - 启用状态: "FIsActive=1"

    推荐 field_keys：
    FRoleID,FName,FNumber,FIsActive,FCreateDate,FDescription

    Returns:
        str: JSON 格式的角色列表
    """
    try:
        result = await _post_system("role", "BD_Role", params.field_keys, params.filter_string, params.start_row, params.limit)
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_permission",
    annotations={"title": "查询权限", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_permission(params: PermissionQueryInput) -> str:
    """查询金蝶系统中的权限列表。

    常用 filter_string：
    - 指定角色: "FRoleId.FNumber='ROLE001'"
    - 指定对象类型: "FObjectType='BD_Material'"

    推荐 field_keys：
    FPermissionId,FName,FNumber,FObjectType,FObjectName,FIsAllow

    Returns:
        str: JSON 格式的权限列表
    """
    try:
        result = await _post_system("permission", "SYS_Permission", params.field_keys, params.filter_string, params.start_row, params.limit)
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_sequence",
    annotations={"title": "查询编码规则", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_sequence(params: SequenceQueryInput) -> str:
    """查询金蝶系统中的编码规则（SequenceRule）列表。

    常用 filter_string：
    - 指定单据类型: "FObjectType='PUR_PurchaseOrder'"
    - 指定编码规则: "FSequenceRuleId.FNumber='SEQ001'"

    推荐 field_keys：
    FSequenceRuleId,FName,FNumber,FObjectType,FDescription,FIsActive

    Returns:
        str: JSON 格式的编码规则列表
    """
    try:
        result = await _post_system("sequence", "SYS_SequenceRule", params.field_keys, params.filter_string, params.start_row, params.limit)
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_number_rule",
    annotations={"title": "查询单据编号规则", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_number_rule(params: NumberRuleQueryInput) -> str:
    """查询金蝶系统中的单据编号规则列表。

    常用 filter_string：
    - 指定单据类型: "FObjectType='SAL_SaleOrder'"
    - 指定规则名: "FNumberRuleId.FNumber='NR001'"

    推荐 field_keys：
    FNumberRuleId,FName,FNumber,FObjectType,FPrefix,FSequenceLength,FDateFormat

    Returns:
        str: JSON 格式的单据编号规则列表
    """
    try:
        result = await _post_system("number_rule", "SYS_NumberRule", params.field_keys, params.filter_string, params.start_row, params.limit)
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_system_config",
    annotations={"title": "查询系统配置", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_system_config(params: SystemConfigInput) -> str:
    """查询金蝶系统中的系统配置参数。

    常用 filter_string：
    - 指定配置项: "FConfigKey='MaxUploadSize'"
    - 指定分类: "FCategory='System'"

    推荐 field_keys：
    FConfigId,FConfigKey,FConfigValue,FDescription,FCategory,FIsActive

    Returns:
        str: JSON 格式的系统配置列表
    """
    try:
        result = await _post_system("sysconfig", "SYS_SystemConfig", params.field_keys, params.filter_string, params.start_row, params.limit)
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
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
        str: JSON 格式的表单列表，含 form_id、名称、描述、推荐字段、数据库表名
    """
    keyword = params.keyword.lower()
    results = []

    for form_id, info in FORM_CATALOG.items():
        # 匹配名称、别名或描述
        if not keyword or (
            keyword in info["name"].lower()
            or any(keyword in alias.lower() for alias in info["alias"])
            or info.get("desc", "").startswith(keyword)
        ):
            results.append({
                "form_id": form_id,
                "name": info["name"],
                "alias": info["alias"],
                "desc": info.get("desc", ""),
                "recommended_fields": info["fields"],
                "db_tables": info.get("db_tables", ()),
                "has_business_rules": bool(info.get("business_rules")),
            })

    return _fmt({
        "count": len(results),
        "tip": (
            "使用 form_id 调用 kingdee_query_bills 查询数据，"
            "或调用 kingdee_get_fields 获取完整字段和业务规则"
        ),
        "forms": results
    })


@mcp.tool(
    name="kingdee_get_fields",
    annotations={"title": "获取表单字段及业务规则", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_get_fields(params: FieldQueryInput) -> str:
    """获取指定表单的完整字段信息和业务规则。

    不知道查询哪些字段时，或需要了解表单的业务限制时，先调用此工具。

    返回内容：
    - recommended_fields: 推荐查询字段
    - field_list: 字段数组
    - db_tables: 对应数据库表名
    - business_rules: 关键业务规则（如下推限制、状态枚举等）

    字段格式说明：
    - FXxx 是普通字段
    - FXxx.FName 是关联字段取名称（例：FSupplierId.FName）
    - FXxx.FNumber 是关联字段取编码（例：FSupplierId.FNumber）
    - FXxx.fstbl_FIRSTKEYFIELDNAME 是关联字段取FID（用于保存/过滤）

    Returns:
        str: JSON 格式的字段信息
    """
    form_id = params.form_id
    info = FORM_CATALOG.get(form_id)

    if info:
        return _fmt({
            "form_id": form_id,
            "name": info["name"],
            "desc": info.get("desc", ""),
            "recommended_fields": info["fields"],
            "field_list": [f.strip() for f in info["fields"].split(",")],
            "db_tables": info.get("db_tables", ()),
            "business_rules": info.get("business_rules", {}),
            "单据状态枚举": {
                "A": "创建",
                "B": "审核中",
                "C": "已审核",
                "D": "重新审核",
                "Z": "暂存",
            },
            "通用状态枚举": {
                "A": "正常/未关闭",
                "B": "已关闭/冻结/终止/业务关闭",
            },
        })
    else:
        # 返回通用建议
        return _fmt({
            "form_id": form_id,
            "name": "未知表单",
            "tip": "此表单不在常用目录中，建议尝试以下通用字段：FID,FBillNo,FNumber,FName,FDate,FDocumentStatus",
            "common_fields": ["FID", "FBillNo", "FNumber", "FName", "FDate", "FDocumentStatus", "FCreateDate", "FModifyDate"],
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
    """审批通过或驳回单据。

    - approve: 审核通过（待审核 → 已审核）
    - reject:  驳回（已审核 → 反审核回到待审核状态）
    - 返回结构化结果，包含 success / next_action 字段

    Returns:
        str: JSON，含 success / action / bill_id 字段
    """
    try:
        if params.action == "approve":
            result = await _post_raw("audit", params.form_id, {"Ids": params.bill_id})
            action_name = "审批通过"
        elif params.action == "reject":
            result = await _post_raw("unaudit", params.form_id, {"Ids": params.bill_id})
            action_name = "审批驳回"
        else:
            return _fmt({"error": f"不支持的操作: {params.action}"})

        status_data = _result_status(result, "audit" if params.action == "approve" else "unaudit")
        status_data["action"] = action_name
        status_data["bill_id"] = params.bill_id
        if params.opinion:
            status_data["opinion"] = params.opinion
        return _fmt(status_data)
    except Exception as e:
        return _err(e, op=params.action)


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
            "start_row": params.start_row,
            "count": len(rows),
            "has_more": len(rows) >= params.limit,
            "data": rows
        })
    except Exception as e:
        return _err(e)


# ─────────────────────────────────────────────
# 资产管理工具
# ─────────────────────────────────────────────

@mcp.tool(name="kingdee_query_fixed_asset", annotations={"title": "查询固定资产", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def kingdee_query_fixed_asset(params: QueryInput) -> str:
    """查询固定资产卡片主数据（FA_FAGet / BD_MainData，formId: FA）。
    固定资产是企业长期使用的有形资产，如房屋、机器设备、运输工具等。
    支持按资产编号、名称、状态、使用部门等条件筛选。
    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定资产编号: "FNumber='FA001'"
    - 指定使用部门: "FUseDeptId.FNumber='D001'"
    - 在用资产: "FStatus='USING'"
    推荐 field_keys：
    FID,FNumber,FName,FAssetSource,FSpecification,FUsedPeriod,FOriginalAmount,FDepreciateRate,FUseDeptId.FName,FDocumentStatus,FStatus
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" else "FID,FNumber,FName,FAssetSource,FSpecification,FUsedPeriod,FOriginalAmount,FDepreciateRate,FUseDeptId.FName,FDocumentStatus,FStatus"
        result = await _post("query", _query_payload("FA_FAGet", fk, params.filter_string, params.order_string, params.start_row, params.limit))
        return _fmt({"form_id": "FA_FAGet", "count": len(_rows(result)), "data": _rows(result)})
    except Exception as e:
        return _err(e)


@mcp.tool(name="kingdee_query_asset_card", annotations={"title": "查询资产卡片", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def kingdee_query_asset_card(params: QueryInput) -> str:
    """查询资产卡片（FA_FAGet 或子单据）。
    资产卡片是固定资产的详细记录，包含原值、累计折旧、净值、卡片状态等信息。
    常用 filter_string：
    - 指定资产编号: "FNumber='FA001'"
    - 指定保管人: "FCustodian.FNumber='EMP001'"
    - 已计提折旧: "FTotalDepreciate>0"
    推荐 field_keys：
    FID,FNumber,FName,FAssetSource,FOriginalAmount,FTotalDepreciate,FNetAmount,FDepreciateMonth,FUsefulLife,FSalvageValue,FCustodian.FName
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" else "FID,FNumber,FName,FAssetSource,FOriginalAmount,FTotalDepreciate,FNetAmount,FDepreciateMonth,FUsefulLife,FSalvageValue,FCustodian.FName"
        result = await _post("query", _query_payload("FA_FAGet", fk, params.filter_string, params.order_string, params.start_row, params.limit))
        return _fmt({"form_id": "FA_FAGet", "count": len(_rows(result)), "data": _rows(result)})
    except Exception as e:
        return _err(e)


@mcp.tool(name="kingdee_query_asset_depreciation", annotations={"title": "查询资产折旧记录", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def kingdee_query_asset_depreciation(params: QueryInput) -> str:
    """查询资产折旧记录（FA_DepreciationBill）。
    折旧记录是固定资产计提折旧的明细，反映每月折旧费用、累计折旧、净值变化。
    常用 filter_string：
    - 指定期间: "FYear=2024 and FPeriod=3"
    - 指定资产: "FAssetId.FNumber='FA001'"
    推荐 field_keys：
    FID,FYear,FPeriod,FAssetId.FNumber,FAssetId.FName,FDepreciateDeptId.FName,FDepreciateAmount,FOriginalAmount,FTotalDepreciate,FNetAmount
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" else "FID,FYear,FPeriod,FAssetId.FNumber,FAssetId.FName,FDepreciateDeptId.FName,FDepreciateAmount,FOriginalAmount,FTotalDepreciate,FNetAmount"
        result = await _post("query", _query_payload("FA_DepreciationBill", fk, params.filter_string, params.order_string, params.start_row, params.limit))
        return _fmt({"form_id": "FA_DepreciationBill", "count": len(_rows(result)), "data": _rows(result)})
    except Exception as e:
        return _err(e)


@mcp.tool(name="kingdee_save_asset", annotations={"title": "新增或修改固定资产", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False})
async def kingdee_save_asset(params: SaveInput) -> str:
    """新增或修改固定资产（FA_FAGet）。
    固定资产新建后状态为"草稿"，需提交+审核后才生效。
    修改已审核资产需要反审核后才能操作。
    """
    try:
        result = await _post("save", [params.form_id, {"Model": params.model, "NeedUpdateFields": params.need_update_fields, "IsDeleteEntry": params.is_delete_entry}])
        return _fmt(_result_status(result, "save"))
    except Exception as e:
        return _err(e, op="save")


@mcp.tool(name="kingdee_query_asset_transfer", annotations={"title": "查询资产调拨单", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def kingdee_query_asset_transfer(params: QueryInput) -> str:
    """查询资产调拨单（FA_Transfer）。
    资产调拨记录固定资产在部门或使用人之间的转移。
    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定资产: "FAssetId.FNumber='FA001'"
    - 原使用部门: "FOldDeptId.FNumber='D001'"
    推荐 field_keys：
    FID,FBillNo,FTransferDate,FDocumentStatus,FAssetId.FNumber,FAssetId.FName,FOldDeptId.FName,FNewDeptId.FName,FTransferReason
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" else "FID,FBillNo,FTransferDate,FDocumentStatus,FAssetId.FNumber,FAssetId.FName,FOldDeptId.FName,FNewDeptId.FName,FTransferReason"
        result = await _post("query", _query_payload("FA_Transfer", fk, params.filter_string, params.order_string, params.start_row, params.limit))
        return _fmt({"form_id": "FA_Transfer", "count": len(_rows(result)), "data": _rows(result)})
    except Exception as e:
        return _err(e)


@mcp.tool(name="kingdee_query_asset_scrape", annotations={"title": "查询资产报废单", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def kingdee_query_asset_scrape(params: QueryInput) -> str:
    """查询资产报废单（FA_Scrape）。
    资产报废记录固定资产的处置，包括正常报废、提前报废、毁损等。
    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定资产: "FAssetId.FNumber='FA001'"
    - 报废类型: "FScrapeType='NORMAL'"
    推荐 field_keys：
    FID,FBillNo,FScrapeDate,FDocumentStatus,FAssetId.FNumber,FAssetId.FName,FOriginalAmount,FTotalDepreciate,FNetAmount,FScrapeType,FHandleMethod
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" else "FID,FBillNo,FScrapeDate,FDocumentStatus,FAssetId.FNumber,FAssetId.FName,FOriginalAmount,FTotalDepreciate,FNetAmount,FScrapeType,FHandleMethod"
        result = await _post("query", _query_payload("FA_Scrape", fk, params.filter_string, params.order_string, params.start_row, params.limit))
        return _fmt({"form_id": "FA_Scrape", "count": len(_rows(result)), "data": _rows(result)})
    except Exception as e:
        return _err(e)


# ─────────────────────────────────────────────
# SCM 供应链工具
# ─────────────────────────────────────────────

@mcp.tool(
    name="kingdee_query_purchase_requisitions",
    annotations={"title": "查询采购申请单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_purchase_requisitions(params: QueryInput) -> str:
    """查询采购申请单（PUR_Requisition）列表。

    采购申请单是采购流程的起点，用于向采购部门提出物料或服务采购需求。
    申请单可下推生成采购订单、采购询价单等。

    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定申请人: "FApplicantId.FNumber='EMP001'"
    - 指定申请部门: "FRequestDeptId.FNumber='D001'"

    推荐 field_keys：
    FID,FBillNo,FDate,FDocumentStatus,FApplicantId.FName,FRequestDeptId.FName,FTotalAmount

    Returns:
        str: JSON 格式的采购申请单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FID,FBillNo,FDate,FDocumentStatus,FApplicantId.FName,FRequestDeptId.FName"
        result = await _post("query", _query_payload(
            "PUR_Requisition", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_sale_quotations",
    annotations={"title": "查询销售报价单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_sale_quotations(params: QueryInput) -> str:
    """查询销售报价单（SAL_Quotation）列表。

    销售报价单是向客户提供的商品或服务价格方案，可作为销售订单的参考或直接下推为销售订单。

    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定客户: "FCustId.FNumber='C001'"

    推荐 field_keys：
    FID,FBillNo,FDate,FDocumentStatus,FCustId.FName,FSalesmanId.FName,FTotalAmount

    Returns:
        str: JSON 格式的销售报价单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FID,FBillNo,FDate,FDocumentStatus,FCustId.FName,FTotalAmount"
        result = await _post("query", _query_payload(
            "SAL_Quotation", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_quality_inspections",
    annotations={"title": "查询来料检验单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_quality_inspections(params: QueryInput) -> str:
    """查洵来料检验单（QIS_InspectBill/IQC）列表。

    来料检验单用于对采购物料进行质量检验，判断是否允许入库。

    常用 filter_string：
    - 已检验: "FDocumentStatus='C'"
    - 检验结果-合格: "FResult='1'" 或 "FPassQty>0"
    - 检验结果-不合格: "FFailQty>0"

    推荐 field_keys：
    FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FMaterialId.FName,FPassQty,FFailQty,FInspectTypeId.FName

    Returns:
        str: JSON 格式的来料检验单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FMaterialId.FName,FPassQty,FFailQty"
        result = await _post("query", _query_payload(
            "QIS_InspectBill", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_stock_transfer_apply",
    annotations={"title": "查询调拨申请单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_stock_transfer_apply(params: QueryInput) -> str:
    """查询调拨申请单（STK_TransferApply）列表。

    调拨申请单用于申请仓库之间物料的转移，经审核后可下推生成调拨单。

    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定调出仓库: "FSendStockId.FNumber='WH01'"
    - 指定调入仓库: "FReceiveStockId.FNumber='WH02'"

    推荐 field_keys：
    FID,FBillNo,FDate,FDocumentStatus,FSendStockId.FName,FReceiveStockId.FName

    Returns:
        str: JSON 格式的调拨申请单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FID,FBillNo,FDate,FDocumentStatus,FSendStockId.FName,FReceiveStockId.FName"
        result = await _post("query", _query_payload(
            "STK_TransferApply", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


# ─────────────────────────────────────────────
# 审计合规工具（Audit & Compliance）
# ─────────────────────────────────────────────

class AuditLogInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(default="", description="单据类型，如 PUR_PurchaseOrder（留空查询所有）")
    bill_id: str = Field(default="", description="单据内码 FID（精确查询）")
    bill_no: str = Field(default="", description="单据编号，支持模糊查询")
    user_name: str = Field(default="", description="审核人，支持模糊查询")
    start_date: str = Field(default="", description="开始日期，格式 YYYY-MM-DD")
    end_date: str = Field(default="", description="结束日期，格式 YYYY-MM-DD")
    result: str = Field(default="", description="审核结果：pass(通过)、reject(驳回)、cancel(取消)、all(全部)")
    filter_string: str = Field(default="", description="额外的过滤条件（Kingdee 查询语法）")
    order_string: str = Field(default="FCREATEDATE DESC", description="排序条件")
    start_row: int = Field(default=0, ge=0, description="分页起始行")
    limit: int = Field(default=50, ge=1, le=2000, description="每页条数，最大2000")


class ChangeLogInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(default="", description="单据类型，如 PUR_PurchaseOrder")
    bill_id: str = Field(default="", description="单据内码 FID")
    bill_no: str = Field(default="", description="单据编号，支持模糊查询")
    user_name: str = Field(default="", description="修改人，支持模糊查询")
    start_date: str = Field(default="", description="开始日期，格式 YYYY-MM-DD")
    end_date: str = Field(default="", description="结束日期，格式 YYYY-MM-DD")
    field_name: str = Field(default="", description="字段名称，如 FQty、FPrice 等")
    filter_string: str = Field(default="", description="额外的过滤条件（Kingdee 查询语法）")
    order_string: str = Field(default="FCREATEDATE DESC", description="排序条件")
    start_row: int = Field(default=0, ge=0, description="分页起始行")
    limit: int = Field(default=50, ge=1, le=2000, description="每页条数，最大2000")


class ApprovalFlowInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    form_id: str = Field(..., description="单据类型，如 PUR_PurchaseOrder")
    bill_id: str = Field(default="", description="单据内码 FID（留空查询该类型所有单据的审批流）")
    bill_no: str = Field(default="", description="单据编号（与 bill_id 二选一）")
    status: str = Field(default="all", description="审批状态：pending(进行中)、approved(已完成)、rejected(已驳回)、all(全部)")
    start_date: str = Field(default="", description="开始日期，格式 YYYY-MM-DD")
    end_date: str = Field(default="", description="结束日期，格式 YYYY-MM-DD")
    filter_string: str = Field(default="", description="额外的过滤条件（Kingdee 查询语法）")
    order_string: str = Field(default="FCREATEDATE DESC", description="排序条件")
    start_row: int = Field(default=0, ge=0, description="分页起始行")
    limit: int = Field(default=50, ge=1, le=2000, description="每页条数，最大2000")


class PermissionChangeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    user_name: str = Field(default="", description="用户名称，支持模糊查询")
    target_type: str = Field(default="", description="授权对象类型：User/Role/Position 等")
    object_type: str = Field(default="", description="被授权对象类型：Form/Bill/Report 等")
    object_name: str = Field(default="", description="被授权对象名称")
    action: str = Field(default="", description="操作类型：Grant/Revoke/Modify 等")
    start_date: str = Field(default="", description="开始日期，格式 YYYY-MM-DD")
    end_date: str = Field(default="", description="结束日期，格式 YYYY-MM-DD")
    filter_string: str = Field(default="", description="额外的过滤条件（Kingdee 查询语法）")
    order_string: str = Field(default="FCREATEDATE DESC", description="排序条件")
    start_row: int = Field(default=0, ge=0, description="分页起始行")
    limit: int = Field(default=50, ge=1, le=2000, description="每页条数，最大2000")


class DataBackupInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    backup_type: str = Field(default="", description="备份类型：Full(完整)、Incremental(增量)、Config(配置) 等")
    status: str = Field(default="", description="备份状态：Success/Failed/Restore 等")
    operator: str = Field(default="", description="操作人，支持模糊查询")
    start_date: str = Field(default="", description="开始日期，格式 YYYY-MM-DD")
    end_date: str = Field(default="", description="结束日期，格式 YYYY-MM-DD")
    filter_string: str = Field(default="", description="额外的过滤条件（Kingdee 查询语法）")
    order_string: str = Field(default="FCREATEDATE DESC", description="排序条件")
    start_row: int = Field(default=0, ge=0, description="分页起始行")
    limit: int = Field(default=50, ge=1, le=2000, description="每页条数，最大2000")


class OperationLogInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    user_name: str = Field(default="", description="操作用户名，支持模糊查询")
    start_date: str = Field(default="", description="开始日期，格式 YYYY-MM-DD")
    end_date: str = Field(default="", description="结束日期，格式 YYYY-MM-DD")
    operate_type: str = Field(default="", description="操作类型，如 Save/Submit/Audit/Delete/View 等")
    bill_no: str = Field(default="", description="关联单据号，支持模糊查询")
    form_name: str = Field(default="", description="表单名称，如 采购订单、销售订单 等")
    filter_string: str = Field(default="", description="额外的过滤条件（Kingdee 查询语法）")
    order_string: str = Field(default="FDATETIME DESC", description="排序条件")
    start_row: int = Field(default=0, ge=0, description="分页起始行")
    limit: int = Field(default=50, ge=1, le=2000, description="每页条数，最大2000")


@mcp.tool(
    name="kingdee_query_audit_log",
    annotations={"title": "查询审计日志", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_audit_log(params: AuditLogInput) -> str:
    """查询金蝶云星空的审计日志（BOS_AuditLog）。

    记录单据的审核操作：谁在什么时候审核了哪张单据、审核结果是什么。
    用于合规审计、审批追溯、反舞弊检查。

    推荐场景：
    - 合规要求：保留所有审核操作的审计轨迹
    - 问题排查：某张单据的审核历史
    - 责任追溯：谁在什么时间通过了/驳回了审批

    返回字段说明：
    - FCREATEDATE: 审核时间
    - FCREATORID: 审核人
    - FOBJECTID: 单据内码
    - FFORMID: 单据类型
    - FAUDITRESULT: 审核结果（通过/驳回/取消）
    - FMEMO: 审核意见

    Returns:
        str: JSON 格式的审计日志列表
    """
    try:
        conditions = []
        if params.form_id:
            conditions.append(f"FFORMID = '{params.form_id}'")
        if params.bill_id:
            conditions.append(f"FOBJECTID = '{params.bill_id}'")
        if params.bill_no:
            conditions.append(f"FOBJECTNO like '%{_escape_sql_like(params.bill_no)}%'")
        if params.user_name:
            conditions.append(f"FCREATORID like '%{_escape_sql_like(params.user_name)}%'")
        if params.start_date:
            conditions.append(f"FCREATEDATE > '{params.start_date} 00:00:00'")
        if params.end_date:
            conditions.append(f"FCREATEDATE < '{params.end_date} 23:59:59'")
        if params.result and params.result != "all":
            result_map = {"pass": "通过", "reject": "驳回", "cancel": "取消"}
            result_val = result_map.get(params.result, params.result)
            conditions.append(f"FAUDITRESULT like '%{result_val}%'")
        if params.filter_string:
            conditions.append(params.filter_string)

        filter_str = " and ".join(conditions) if conditions else ""

        result = await _post("query", _query_payload(
            "BOS_AuditLog",
            "FID,FCREATEDATE,FCREATORID,FOBJECTID,FFORMID,FOBJECTNO,FAUDITRESULT,FMEMO",
            filter_str,
            params.order_string,
            params.start_row,
            params.limit
        ))
        rows = _rows(result)

        return _fmt({
            "form_id": "BOS_AuditLog",
            "count": len(rows),
            "has_more": len(rows) == params.limit,
            "filter_summary": {
                "form_id": params.form_id or "全部",
                "bill_id": params.bill_id,
                "bill_no": params.bill_no,
                "user_name": params.user_name,
                "date_range": f"{params.start_date or '~'} ~ {params.end_date or '至今'}",
                "result": params.result or "全部",
            },
            "data": rows,
        })
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_operation_logs",
    annotations={"title": "查询操作日志", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_operation_logs(params: OperationLogInput) -> str:
    """查询金蝶云星空的上机操作日志（BOS_OperateLog）。

    记录用户在系统中的所有操作：登录、登出、进入业务对象、业务操作等。
    用于安全审计、故障排查、操作追溯。

    推荐场景：
    - 排查某张单据是谁在什么时候操作的
    - 安全审计：检查异常登录或批量操作
    - 合规要求：追溯敏感操作记录

    返回字段说明：
    - FDATETIME: 操作时间
    - FUSERID: 操作用户
    - FCOMPUTERNAME: 机器名称
    - FCLIENTIP: 客户端IP
    - FENVIRONMENT: 操作场景（0=登入系统, 1=进入业务对象, 3=业务操作, 4=登出系统）
    - FOPERATENAME: 操作名称（登录/单据查询/批量保存等）
    - FDESCRIPTION: 操作描述
    - FInterId: 对象内码（关联单据号）
    - FTimeConsuming: 耗时(毫秒)
    - FClientType: 客户端类型

    Returns:
        str: JSON 格式的操作日志列表
    """
    try:
        conditions = []
        if params.user_name:
            conditions.append(f"FUSERID like '%{_escape_sql_like(params.user_name)}%'")
        if params.start_date:
            conditions.append(f"FDATETIME > '{params.start_date} 00:00:00'")
        if params.end_date:
            conditions.append(f"FDATETIME < '{params.end_date} 23:59:59'")
        if params.operate_type:
            conditions.append(f"FOPERATENAME like '%{_escape_sql_like(params.operate_type)}%'")
        if params.bill_no:
            conditions.append(f"FInterId like '%{_escape_sql_like(params.bill_no)}%'")
        if params.form_name:
            conditions.append(f"FDESCRIPTION like '%{_escape_sql_like(params.form_name)}%'")
        if params.filter_string:
            conditions.append(params.filter_string)

        filter_str = " and ".join(conditions) if conditions else ""

        result = await _post("query", _query_payload(
            "BOS_OperateLog",
            "FID,FDATETIME,FUSERID,FCOMPUTERNAME,FCLIENTIP,FENVIRONMENT,FOPERATENAME,FDESCRIPTION,FInterId,FTimeConsuming,FClientType",
            filter_str,
            params.order_string,
            params.start_row,
            params.limit
        ))
        rows = _rows(result)

        date_range = f"{params.start_date or '~'} ~ {params.end_date or '至今'}" if params.start_date or params.end_date else "全部"

        return _fmt({
            "form_id": "BOS_OperateLog",
            "count": len(rows),
            "has_more": len(rows) == params.limit,
            "filter_summary": {
                "user_name": params.user_name,
                "date_range": date_range,
                "operate_type": params.operate_type or "全部",
                "bill_no": params.bill_no,
            },
            "data": rows,
        })
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_change_log",
    annotations={"title": "查询变更记录", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_change_log(params: ChangeLogInput) -> str:
    """查询金蝶云星空的单据变更记录（BOS_ModifyLog）。

    记录单据字段的修改历史：谁在什么时候修改了什么字段、从什么值改成了什么值。
    用于数据变更追溯、合规审计、问题排查。

    推荐场景：
    - 数据治理：追踪关键字段的变更历史
    - 问题排查：某张单据的修改记录
    - 合规要求：保留重要数据的修改轨迹

    返回字段说明：
    - FCREATEDATE: 修改时间
    - FCREATORID: 修改人
    - FOBJECTID: 单据内码
    - FFIELDNAME: 字段名称
    - FOLDVALUE: 修改前的值
    - FNEWVALUE: 修改后的值

    Returns:
        str: JSON 格式的变更记录列表
    """
    try:
        conditions = []
        if params.form_id:
            conditions.append(f"FFORMID = '{params.form_id}'")
        if params.bill_id:
            conditions.append(f"FOBJECTID = '{params.bill_id}'")
        if params.bill_no:
            conditions.append(f"FOBJECTNO like '%{_escape_sql_like(params.bill_no)}%'")
        if params.user_name:
            conditions.append(f"FCREATORID like '%{_escape_sql_like(params.user_name)}%'")
        if params.start_date:
            conditions.append(f"FCREATEDATE > '{params.start_date} 00:00:00'")
        if params.end_date:
            conditions.append(f"FCREATEDATE < '{params.end_date} 23:59:59'")
        if params.field_name:
            conditions.append(f"FFIELDNAME like '%{_escape_sql_like(params.field_name)}%'")
        if params.filter_string:
            conditions.append(params.filter_string)

        filter_str = " and ".join(conditions) if conditions else ""

        result = await _post("query", _query_payload(
            "BOS_ModifyLog",
            "FID,FCREATEDATE,FCREATORID,FOBJECTID,FFORMID,FOBJECTNO,FFIELDNAME,FOLDVALUE,FNEWVALUE",
            filter_str,
            params.order_string,
            params.start_row,
            params.limit
        ))
        rows = _rows(result)

        return _fmt({
            "form_id": "BOS_ModifyLog",
            "count": len(rows),
            "has_more": len(rows) == params.limit,
            "filter_summary": {
                "form_id": params.form_id or "全部",
                "bill_id": params.bill_id,
                "bill_no": params.bill_no,
                "user_name": params.user_name,
                "field_name": params.field_name,
                "date_range": f"{params.start_date or '~'} ~ {params.end_date or '至今'}",
            },
            "data": rows,
        })
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_approval_flow",
    annotations={"title": "查询审批流程", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_approval_flow(params: ApprovalFlowInput) -> str:
    """查询金蝶云星空的审批流程记录。

    记录单据从提交到最终审核的完整审批轨迹，包括每个节点的审批人、时间、结果和意见。
    用于审批追溯、流程优化、合规检查。

    推荐场景：
    - 审批追溯：某张单据走过了哪些审批节点
    - 流程优化：分析审批时长和瓶颈
    - 合规检查：确认关键单据是否按流程审批

    注意：金蝶审批流程数据可能存储在多个表单中，
    如 V_SFA_ApprovalRecord（审批记录）、Workflow_Instance（流程实例）等。
    如查询无结果，请用 kingdee_get_fields 查看实际可用字段。

    Returns:
        str: JSON 格式的审批流程列表
    """
    try:
        conditions = []
        conditions.append(f"FFORMID = '{params.form_id}'")
        if params.bill_id:
            conditions.append(f"FOBJECTID = '{params.bill_id}'")
        if params.bill_no:
            conditions.append(f"FOBJECTNO like '%{_escape_sql_like(params.bill_no)}%'")
        if params.start_date:
            conditions.append(f"FCREATEDATE > '{params.start_date} 00:00:00'")
        if params.end_date:
            conditions.append(f"FCREATEDATE < '{params.end_date} 23:59:59'")
        if params.status and params.status != "all":
            status_map = {
                "pending": "审批中",
                "approved": "已通过",
                "rejected": "已驳回",
            }
            status_val = status_map.get(params.status, params.status)
            conditions.append(f"FRESULT like '%{status_val}%'")
        if params.filter_string:
            conditions.append(params.filter_string)

        filter_str = " and ".join(conditions) if conditions else ""

        result = await _post("query", _query_payload(
            "V_SFA_ApprovalRecord",
            "FID,FCREATEDATE,FCREATORID,FOBJECTID,FFORMID,FOBJECTNO,FNODEID,FNODENAME,FAPPROVERID,"
            "FAPPROVERNAME,FAPPROVEDATE,FRESULT,FOPINION,FREMARK",
            filter_str,
            params.order_string,
            params.start_row,
            params.limit
        ))
        rows = _rows(result)

        if not rows:
            result = await _post("query", _query_payload(
                "Workflow_Instance",
                "FID,FCREATEDATE,FUSERID,FFORMID,FObjectId,FObjectNo,FWorkflowId,FWorkflowName,"
                "FNodeId,FNodeName,FApproverId,FApproverName,FApproveDate,FResult,FOpinion",
                filter_str,
                params.order_string,
                params.start_row,
                params.limit
            ))
            rows = _rows(result)

        return _fmt({
            "form_id": "V_SFA_ApprovalRecord / Workflow_Instance",
            "count": len(rows),
            "has_more": len(rows) == params.limit,
            "filter_summary": {
                "form_id": params.form_id,
                "bill_id": params.bill_id,
                "bill_no": params.bill_no,
                "status": params.status,
                "date_range": f"{params.start_date or '~'} ~ {params.end_date or '至今'}",
            },
            "data": rows,
        })
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_permission",
    annotations={"title": "查询权限变更", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_permission(params: PermissionChangeInput) -> str:
    """查询金蝶云星空的权限变更记录。

    记录用户权限的授予、撤销、修改操作。
    用于安全审计、合规检查、权限追溯。

    推荐场景：
    - 安全审计：谁在什么时候被授予/撤销了什么权限
    - 合规要求：保留权限变更的审计轨迹
    - 问题排查：某用户无法访问某功能的原因

    注意：金蝶权限数据可能存储在多个表单中，
    如 SEC_Permission（权限记录）、SEC_UserRole（用户角色关系）等。
    如查询无结果，请用 kingdee_get_fields 查看实际可用字段。

    Returns:
        str: JSON 格式的权限变更列表
    """
    try:
        conditions = []
        if params.user_name:
            conditions.append(f"FUSERNAME like '%{_escape_sql_like(params.user_name)}%'")
        if params.target_type:
            conditions.append(f"FTARGETTYPE like '%{_escape_sql_like(params.target_type)}%'")
        if params.object_type:
            conditions.append(f"FOBJECTTYPE like '%{_escape_sql_like(params.object_type)}%'")
        if params.object_name:
            conditions.append(f"FOBJECTNAME like '%{_escape_sql_like(params.object_name)}%'")
        if params.action:
            conditions.append(f"FACTION like '%{_escape_sql_like(params.action)}%'")
        if params.start_date:
            conditions.append(f"FCREATEDATE > '{params.start_date} 00:00:00'")
        if params.end_date:
            conditions.append(f"FCREATEDATE < '{params.end_date} 23:59:59'")
        if params.filter_string:
            conditions.append(params.filter_string)

        filter_str = " and ".join(conditions) if conditions else ""

        result = await _post("query", _query_payload(
            "SEC_Permission",
            "FID,FCREATEDATE,FCREATORID,FUSERNAME,FTARGETTYPE,FOBJECTTYPE,FOBJECTID,FOBJECTNAME,FACTION,FPRIVILEGE",
            filter_str,
            params.order_string,
            params.start_row,
            params.limit
        ))
        rows = _rows(result)

        if not rows:
            result = await _post("query", _query_payload(
                "SEC_UserRole",
                "FID,FCREATEDATE,FCREATORID,FUSERID,FUSERNAME,FROLEID,FROLENAME,FACTION",
                filter_str,
                params.order_string,
                params.start_row,
                params.limit
            ))
            rows = _rows(result)

        return _fmt({
            "form_id": "SEC_Permission / SEC_UserRole",
            "count": len(rows),
            "has_more": len(rows) == params.limit,
            "filter_summary": {
                "user_name": params.user_name,
                "target_type": params.target_type,
                "object_type": params.object_type,
                "object_name": params.object_name,
                "action": params.action,
                "date_range": f"{params.start_date or '~'} ~ {params.end_date or '至今'}",
            },
            "data": rows,
        })
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_data_backup",
    annotations={"title": "查询数据备份记录", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_data_backup(params: DataBackupInput) -> str:
    """查询金蝶云星空的数据备份记录。

    记录系统的数据备份和恢复操作。
    用于灾备验证、合规检查、恢复演练。

    推荐场景：
    - 灾备验证：确认备份是否按计划执行
    - 合规要求：保留备份操作的审计轨迹
    - 恢复演练：查找可用的备份点

    注意：金蝶备份数据可能存储在系统配置表或其他后台表单中，
    如需访问请确认当前用户有系统管理权限。
    如查询无结果，请用 kingdee_get_fields 查看实际可用字段。

    Returns:
        str: JSON 格式的数据备份记录列表
    """
    try:
        conditions = []
        if params.backup_type:
            conditions.append(f"FBACKUPTYPE like '%{_escape_sql_like(params.backup_type)}%'")
        if params.status:
            conditions.append(f"FSTATUS like '%{_escape_sql_like(params.status)}%'")
        if params.operator:
            conditions.append(f"FOPERATOR like '%{_escape_sql_like(params.operator)}%'")
        if params.start_date:
            conditions.append(f"FBACKUPDATE > '{params.start_date} 00:00:00'")
        if params.end_date:
            conditions.append(f"FBACKUPDATE < '{params.end_date} 23:59:59'")
        if params.filter_string:
            conditions.append(params.filter_string)

        filter_str = " and ".join(conditions) if conditions else ""

        result = await _post("query", _query_payload(
            "DB_BackupRecord",
            "FID,FBACKUPDATE,FOPERATOR,FBACKUPTYPE,FSTATUS,FBACKUPFILE,FBACKUPSIZE,FREMARK",
            filter_str,
            params.order_string,
            params.start_row,
            params.limit
        ))
        rows = _rows(result)

        if not rows:
            result = await _post("query", _query_payload(
                "T_BAS_BackupRecord",
                "FID,FCREATEDATE,FCREATORID,FOPERATOR,FBACKUPTYPE,FSTATUS,FPATH,FSIZE",
                filter_str,
                params.order_string,
                params.start_row,
                params.limit
            ))
            rows = _rows(result)

        return _fmt({
            "form_id": "DB_BackupRecord / T_BAS_BackupRecord",
            "count": len(rows),
            "has_more": len(rows) == params.limit,
            "filter_summary": {
                "backup_type": params.backup_type or "全部",
                "status": params.status or "全部",
                "operator": params.operator,
                "date_range": f"{params.start_date or '~'} ~ {params.end_date or '至今'}",
            },
            "data": rows,
        })
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_purchase_inquiry",
    annotations={"title": "查询采购询价单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_purchase_inquiry(params: QueryInput) -> str:
    """查洵采购询价单（SVM_InquiryBill/RFQ）列表。

    采购询价单（Request for Quotation）用于向供应商询价，收集报价信息。

    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定供应商: "FSupplierId.FNumber='S001'"

    推荐 field_keys：
    FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FMaterialId.FName,FPrice

    Returns:
        str: JSON 格式的询价单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName"
        result = await _post("query", _query_payload(
            "SVM_InquiryBill", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_supplier_quotes",
    annotations={"title": "查询供应商报价单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_supplier_quotes(params: QueryInput) -> str:
    """查洵供应商报价单（SVM_QuoteBill）列表。

    供应商报价单是供应商对询价单的响应，包含物料价格信息。
    可用于比价分析，选择最优供应商。

    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定供应商: "FSupplierId.FNumber='S001'"
    - 指定物料: "FMaterialId.FNumber='MAT001'"

    推荐 field_keys：
    FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FMaterialId.FName,FPrice,FQuantity

    Returns:
        str: JSON 格式的报价单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FID,FBillNo,FDate,FDocumentStatus,FSupplierId.FName,FMaterialId.FName,FPrice"
        result = await _post("query", _query_payload(
            "SVM_QuoteBill", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)




# ─────────────────────────────────────────────
# 杂项出入库和调拨工具
# ─────────────────────────────────────────────

@mcp.tool(
    name="kingdee_query_misc_movement_detail",
    annotations={"title": "查询杂项出入库明细表", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_misc_movement_detail(params: QueryInput) -> str:
    """查询杂项出入库明细表（STK_MiscMovementDetail）。

    用于查看杂项出入库的明细数据，包括其他入库、其他出库等。

    常用 filter_string：
    - 指定日期范围: "FBillDate>='2024-01-01' and FBillDate<='2024-12-31'"
    - 指定物料: "FMaterialId.FNumber='MAT001'"
    - 指定仓库: "FStockId.FNumber='WH01'"

    推荐 field_keys（默认已包含关键字段）：
    FID,FBillNo,FBillDate,FDocumentStatus,FStockOrgId.FName,
    FMaterialId.FNumber,FMaterialId.FName,FUnitId.FName,FQty,FPrice,FAmount

    Returns:
        str: JSON 格式的杂项出入库明细列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else (
                "FID,FBillNo,FBillDate,FDocumentStatus,FStockOrgId.FName,"
                "FMaterialId.FNumber,FMaterialId.FName,FUnitId.FName,"
                "FQty,FPrice,FAmount"
            )
        result = await _post("query", _query_payload(
            "STK_MiscMovementDetail", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({
            "form_id": "STK_MiscMovementDetail",
            "count": len(rows),
            "has_more": len(rows) == params.limit,
            "data": rows
        })
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_transfer_pending_detail",
    annotations={"title": "查询分步式调出未调入明细", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_transfer_pending_detail(params: QueryInput) -> str:
    """查询分步式调出未调入明细表（STK_TransferPendingDetail）。

    用于查看分步式调拨流程中，已调出但未调入的单据明细。

    常用 filter_string：
    - 指定调出日期范围: "FOutDate>='2024-01-01' and FOutDate<='2024-12-31'"
    - 指定物料: "FMaterialId.FNumber='MAT001'"
    - 指定调出仓库: "FOutStockId.FNumber='WH01'"

    推荐 field_keys（默认已包含关键字段）：
    FID,FBillNo,FOutDate,FInDate,FDocumentStatus,FStockOrgId.FName,
    FOutStockId.FName,FInStockId.FName,FMaterialId.FNumber,FMaterialId.FName,
    FUnitId.FName,FOutQty,FInQty,FPendingQty

    Returns:
        str: JSON 格式的分步式调出未调入明细列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else (
                "FID,FBillNo,FOutDate,FInDate,FDocumentStatus,FStockOrgId.FName,"
                "FOutStockId.FName,FInStockId.FName,FMaterialId.FNumber,FMaterialId.FName,"
                "FUnitId.FName,FOutQty,FInQty,FPendingQty"
            )
        result = await _post("query", _query_payload(
            "STK_TransferPendingDetail", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({
            "form_id": "STK_TransferPendingDetail",
            "count": len(rows),
            "has_more": len(rows) == params.limit,
            "data": rows
        })
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_transfer_apply",
    annotations={"title": "查询调拨申请单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_transfer_apply(params: QueryInput) -> str:
    """查询调拨申请单（STK_TransferApply）列表。

    调拨申请单是调拨业务的起点，可下推生成直接调拨单或分步式调拨单。

    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定日期范围: "FBillDate>='2024-01-01' and FBillDate<='2024-12-31'"
    - 指定调出仓库: "FOutStockId.FNumber='WH01'"
    - 指定调入仓库: "FInStockId.FNumber='WH02'"
    - 未关闭: "FCloseStatus='A' and FBusinessClose='A'"

    推荐 field_keys（默认已包含关键字段）：
    FID,FBillNo,FBillDate,FDocumentStatus,FStockOrgId.FName,
    FOutStockId.FName,FInStockId.FName,FTransferType,
    FMaterialId.FNumber,FMaterialId.FName,FUnitId.FName,FQty,FPrice,FAmount

    Returns:
        str: JSON 格式的调拨申请单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else (
                "FID,FBillNo,FBillDate,FDocumentStatus,FStockOrgId.FName,"
                "FOutStockId.FName,FInStockId.FName,FTransferType,"
                "FMaterialId.FNumber,FMaterialId.FName,FUnitId.FName,FQty,FPrice,FAmount"
            )
        result = await _post("query", _query_payload(
            "STK_TransferApply", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({
            "form_id": "STK_TransferApply",
            "count": len(rows),
            "has_more": len(rows) == params.limit,
            "data": rows
        })
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_transfer_direct",
    annotations={"title": "查询直接调拨单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_transfer_direct(params: QueryInput) -> str:
    """查询直接调拨单（STK_TransferDirect）列表。

    直接调拨单用于一步完成调拨业务，同时更新调出仓和调入仓库存。

    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定日期范围: "FBillDate>='2024-01-01' and FBillDate<='2024-12-31'"
    - 指定调出仓库: "FOutStockId.FNumber='WH01'"
    - 指定调入仓库: "FInStockId.FNumber='WH02'"
    - 未关闭: "FCloseStatus='A' and FBusinessClose='A'"

    推荐 field_keys（默认已包含关键字段）：
    FID,FBillNo,FBillDate,FDocumentStatus,FStockOrgId.FName,
    FOutStockId.FName,FInStockId.FName,FMaterialId.FNumber,
    FMaterialId.FName,FUnitId.FName,FQty,FPrice,FAmount

    Returns:
        str: JSON 格式的直接调拨单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else (
                "FID,FBillNo,FBillDate,FDocumentStatus,FStockOrgId.FName,"
                "FOutStockId.FName,FInStockId.FName,FMaterialId.FNumber,"
                "FMaterialId.FName,FUnitId.FName,FQty,FPrice,FAmount"
            )
        result = await _post("query", _query_payload(
            "STK_TransferDirect", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({
            "form_id": "STK_TransferDirect",
            "count": len(rows),
            "has_more": len(rows) == params.limit,
            "data": rows
        })
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_push_stock_transfer",
    annotations={"title": "调拨申请下推调拨单", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_push_stock_transfer(params: PushDownInput) -> str:
    """从调拨申请单下推到直接调拨单（STK_TransferApply -> STK_TransferDirect）。

    用于将调拨申请单下推生成直接调拨单，一步完成调拨。

    参数说明：
    - form_id: 固定为 STK_TransferApply（调拨申请单）
    - target_form_id: 固定为 STK_TransferDirect（直接调拨单）
    - source_bill_nos: 调拨申请单的单据编号列表

    转换规则说明：
    - 默认（rule_id=空）：使用系统配置的默认转换规则
    - enable_default_rule=true：强制启用默认下推规则
    - rule_id 显式指定：绕过默认规则，使用指定规则

    响应包含：
    - Result.ResponseStatus：保存结果（IsSuccess 判断整体是否成功）
    - Result.ConvertResponseStatus：每行下推转换结果

    Returns:
        str: JSON，含 success / bill_nos / next_action 字段
    """
    try:
        push_data: dict[str, Any] = {
            "TargetFormId": "STK_TransferDirect",
            "Numbers": params.source_bill_nos,
        }
        if params.rule_id:
            push_data["RuleId"] = params.rule_id
        if params.enable_default_rule:
            push_data["IsEnableDefaultRule"] = "true"
        if params.draft_on_fail:
            push_data["IsDraftWhenSaveFail"] = "true"
        result = await _post_raw("push", "STK_TransferApply", push_data)
        status_data = _result_status(result, "push")
        rs = result.get("Result", result) if isinstance(result, dict) else {}
        numbers = rs.get("Numbers", [])
        ids = rs.get("Ids", [])
        if status_data.get("success"):
            status_data["source_bill_nos"] = params.source_bill_nos
            status_data["target_form_id"] = "STK_TransferDirect"
            if numbers:
                status_data["target_bill_nos"] = numbers
            if ids:
                status_data["target_fids"] = ids if isinstance(ids, list) else [ids]
            status_data["tip"] = (
                f"已生成 {len(numbers)} 张直接调拨单，"
                "请依次调用 kingdee_submit_bills + kingdee_audit_bills 完成提交和审核"
            )
        return _fmt(status_data)
    except Exception as e:
        return _err(e, op="push")


# ─────────────────────────────────────────────
# Prompts（内置提示词模板）
# ─────────────────────────────────────────────

@mcp.prompt(name="查询采购订单")
def prompt_query_purchase_orders() -> list[UserMessage]:
    """查询已审核采购订单的提示词模板"""
    return [
        UserMessage(
            content="请帮我查询最近20条已审核的采购订单，"
                    "包含单据号、日期、供应商名称和金额，按日期倒序排列。"
        )
    ]


@mcp.prompt(name="查询即时库存")
def prompt_query_inventory() -> list[UserMessage]:
    """查询当前库存的提示词模板"""
    return [
        UserMessage(
            content="请查询当前所有有库存（数量大于0）的物料，"
                    "列出物料编码、名称、仓库和数量。"
        )
    ]


@mcp.prompt(name="新建采购订单")
def prompt_create_purchase_order() -> list[UserMessage]:
    """新建采购订单的提示词模板"""
    return [
        UserMessage(
            content="请帮我新建一张采购订单。需要提供以下信息：\n"
                    "1. 供应商编码（如 S001）\n"
                    "2. 物料编码（如 MAT001）\n"
                    "3. 数量\n"
                    "4. 单价\n"
                    "5. 采购部门编码（如 D001）\n"
                    "请告诉我以上信息，我来帮你创建。"
        )
    ]


# ─────────────────────────────────────────────
# Resources（上下文资源）
# ─────────────────────────────────────────────

@mcp.resource("kingdee://forms", mime_type="application/json")
def resource_form_catalog() -> str:
    """金蝶常用表单目录，包含 form_id、中文名称、描述和推荐查询字段"""
    return json.dumps(
        [{
            "form_id": k,
            "name": v["name"],
            "alias": v["alias"],
            "desc": v.get("desc", ""),
            "recommended_fields": v["fields"],
            "db_tables": v.get("db_tables", ()),
            "has_business_rules": bool(v.get("business_rules")),
        } for k, v in FORM_CATALOG.items()],
        ensure_ascii=False, indent=2
    )


@mcp.resource("kingdee://help", mime_type="text/plain; charset=utf-8")
def resource_help() -> str:
    """金蝶 MCP Server 使用指南"""
    return """金蝶 MCP Server 使用指南
====================

## 供应链（SCM）查询
- kingdee_query_purchase_orders          查询采购订单列表（默认含关联数量/累计入库）
- kingdee_query_purchase_order_progress 查询采购订单执行进度（表体分录级）
- kingdee_query_purchase_requisitions    查询采购申请单
- kingdee_query_purchase_inquiry         查询采购询价单（RFQ）
- kingdee_query_supplier_quotes          查询供应商报价单
- kingdee_query_sale_orders              查询销售订单
- kingdee_query_sale_quotations          查询销售报价单
- kingdee_query_stock_bills              查询出入库单
- kingdee_query_stock_transfer_apply     查询调拨申请单
- kingdee_query_inventory                查询即时库存
- kingdee_query_quality_inspections     查询来料检验单（IQC）

## 基础资料查询
- kingdee_query_materials    查询物料档案
- kingdee_query_partners     查询客户/供应商

## 通用查询
- kingdee_query_bills        通用单据查询（任意 form_id）

## 写操作（会修改 ERP 数据）
- kingdee_save_bill      新建或修改单据
- kingdee_submit_bills   提交单据
- kingdee_audit_bills    审核单据
- kingdee_unaudit_bills  反审核单据
- kingdee_delete_bills   删除单据
- kingdee_push_bill      下推单据（采购订单→收料通知单/入库单；销售订单→出库单）

## 采购订单核心业务规则
- 关联数量 = 累计收料数量 + 累计入库数量
- 关联数量 >= 订单数量 → 无法下推收料单/入库单
- 勾选控制交货数量 → 关联数量 >= 交货下限无法下推，超交货上限无法保存
- 累计入库数量 >= 交货下限 → 该行自动业务关闭
- 冻结/终止的分录行不允许编辑和关联操作
- 采购订单被付款单关联后，不可反审核

## 销售订单核心业务规则
- 累计出库数量 >= 订单数量 → 该行自动业务关闭
- 冻结/终止的分录行不允许编辑和关联操作

## 采购入库单核心业务规则
- 入库单审核时累加采购订单【累计入库数量】；反审核时扣减
- 勾选控制交货数量时，入库数量不能超过采购订单【交货上限】

## 来料检验核心业务规则
- 物料勾选来料检验时，必须先收料检验合格后再入库
- 合格物料下推入库单至合格品仓库；不合格物料走特采或退货流程

## 单据状态枚举
- A=创建 B=审核中 C=已审核 D=重新审核 Z=暂存
- 业务状态 A=正常 B=业务关闭/冻结/终止

## 元数据
- kingdee_list_forms   搜索可用表单（不知道 form_id 时先用这个）
- kingdee_get_fields  获取表单字段列表及业务规则

## SQL 数据库探查
- kingdee_discover_tables            搜索表名
- kingdee_discover_columns            搜索列名
- kingdee_describe_table              查看表结构
- kingdee_discover_metadata_candidates 查看 form_id 对应的数据库表

## 常用 filter_string 示例
- 已审核: FDocumentStatus='C'
- 指定日期: FDate>='2024-01-01' and FDate<='2024-12-31'
- 模糊搜索: FName like '%关键词%'
- 未关闭: FCloseStatus='A'
- 业务正常: FBusinessClose='A'

## 成本管理（需启用成本模块）
- kingdee_query_material_cost              查询物料成本库
- kingdee_query_cost_calculation         查询成本计算单
- kingdee_query_cost_centers             查询成本中心
- kingdee_query_cost_items              查询成本项目
- kingdee_query_product_standard_cost    查询产品标准成本
"""


# ─────────────────────────────────────────────
# 成本管理工具（存货核算、产品成本、标准成本）
# ─────────────────────────────────────────────

class MaterialCostQueryInput(QueryInput):
    """物料成本库查询输入模型"""
    pass


@mcp.tool(
    name="kingdee_query_material_cost",
    annotations={"title": "查询物料成本库", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_material_cost(params: QueryInput) -> str:
    """查询物料成本库（BD_MaterialCost）。

    返回物料的标准成本、最新成本、平均成本等信息。

    常用 filter_string：
    - 指定物料: "FMaterialId.FNumber='MAT001'"
    - 指定成本组织: "FCostOrgId.FNumber='100'"

    推荐 field_keys：
    FMaterialId.FNumber,FMaterialId.FName,FUnitId.FName,FStdCost,FLatestCost,FAvgCost

    Returns:
        str: JSON 格式的物料成本列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FMaterialId.FNumber,FMaterialId.FName,FUnitId.FName,FStdCost,FLatestCost,FAvgCost"
        result = await _post("query", _query_payload(
            "BD_MaterialCost", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_material_target_cost",
    annotations={"title": "查询物料目标成本单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_material_target_cost(params: QueryInput) -> str:
    """查询物料目标成本单（BD_MatTargetCost）。

    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定物料: "FMaterialId.FNumber='MAT001'"

    推荐 field_keys：
    FBillNo,FDate,FDocumentStatus,FMaterialId.FNumber,FMaterialId.FName,FTargetCost

    Returns:
        str: JSON 格式的目标成本单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FBillNo,FDate,FDocumentStatus,FMaterialId.FNumber,FMaterialId.FName,FTargetCost"
        result = await _post("query", _query_payload(
            "BD_MatTargetCost", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_cost_calculation",
    annotations={"title": "查询成本计算单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_cost_calculation(params: QueryInput) -> str:
    """查询成本计算单（CB_CostCalBill）列表。

    常用 filter_string：
    - 指定年度: "FYear=2024"
    - 指定期间: "FPeriod='01'"
    - 指定物料: "FMaterialId.FNumber='MAT001'"

    推荐 field_keys：
    FYear,FPeriod,FMaterialId.FNumber,FMaterialId.FName,FCostAmt,FMaterialCost,FLabourCost

    Returns:
        str: JSON 格式的成本计算单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FYear,FPeriod,FMaterialId.FNumber,FMaterialId.FName,FCostAmt,FMaterialCost,FLabourCost"
        result = await _post("query", _query_payload(
            "CB_CostCalBill", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_cost_centers",
    annotations={"title": "查询成本中心", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_cost_centers(params: QueryInput) -> str:
    """查询成本中心基础资料（CB_CostCenter）。

    常用 filter_string：
    - 指定编码: "FNumber like 'CC%'"
    - 启用状态: "FIsActive='1'"

    推荐 field_keys：
    FNumber,FName,FDeptId.FName,FIsActive

    Returns:
        str: JSON 格式的成本中心列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FNumber,FName,FDeptId.FName,FIsActive"
        result = await _post("query", _query_payload(
            "CB_CostCenter", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_cost_items",
    annotations={"title": "查询成本项目", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_cost_items(params: QueryInput) -> str:
    """查询成本项目基础资料（CB_CostItem）。

    常用 filter_string：
    - 指定编码: "FNumber like 'CI%'"
    - 成本项目类型: "FCostItemType='1'"

    推荐 field_keys：
    FNumber,FName,FCostItemType,FIsActive

    Returns:
        str: JSON 格式的成本项目列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FNumber,FName,FCostItemType,FIsActive"
        result = await _post("query", _query_payload(
            "CB_CostItem", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_product_standard_cost",
    annotations={"title": "查询产品标准成本", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_product_standard_cost(params: QueryInput) -> str:
    """查询产品标准成本（STD_ProductCostQuery）。

    常用 filter_string：
    - 指定物料: "FMaterialId.FNumber='MAT001'"
    - 指定成本版本: "FCostVersionId.FNumber='STD01'"

    推荐 field_keys：
    FMaterialId.FNumber,FMaterialId.FName,FUnitId.FName,FStdCost,FMaterialCost,FLabourCost,FFeeCost

    Returns:
        str: JSON 格式的产品标准成本列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FMaterialId.FNumber,FMaterialId.FName,FUnitId.FName,FStdCost,FMaterialCost,FLabourCost,FFeeCost"
        result = await _post("query", _query_payload(
            "STD_ProductCostQuery", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_cost_adjustments",
    annotations={"title": "查询成本调整单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_cost_adjustments(params: QueryInput) -> str:
    """查询成本调整单（STK_CostAdjust）。

    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定调整类型: "FAdjustType='1'"

    推荐 field_keys：
    FBillNo,FDate,FDocumentStatus,FCostOrgId.FNumber,FCostOrgId.FName,FAdjustType,FAdjustAmount

    Returns:
        str: JSON 格式的成本调整单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FBillNo,FDate,FDocumentStatus,FCostOrgId.FNumber,FCostOrgId.FName,FAdjustType,FAdjustAmount"
        result = await _post("query", _query_payload(
            "STK_CostAdjust", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_save_cost_adjustment",
    annotations={"title": "保存成本调整单", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_save_cost_adjustment(params: SaveInput) -> str:
    """新建或修改成本调整单（STK_CostAdjust）。

    model 示例：
    {
      "FDate": "2024-01-15",
      "FCostOrgId": {"FNumber": "100"},
      "FAdjustType": "1",
      "FCostAdjustEntry": [
        {"FMaterialId": {"FNumber": "MAT001"}, "FAdjustQty": 100, "FAdjustPrice": 10.5}
      ]
    }

    Returns:
        str: JSON，含 FID 和 FBillNo
    """
    try:
        model = dict(params.model)
        model.setdefault("FID", 0)
        result = await _post_raw(
            "save", "STK_CostAdjust", model,
            need_return_fields=["FID", "FBillNo"],
        )
        status_data = _result_status(result, "save")
        if status_data.get("success"):
            status_data["tip"] = "成本调整单已保存，需要提交+审核后才能生效"
        return _fmt(status_data)
    except Exception as e:
        return _err(e, op="save")


@mcp.tool(
    name="kingdee_query_instant_cost_compare",
    annotations={"title": "即时成本对比分析", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_instant_cost_compare(params: QueryInput) -> str:
    """查询即时成本对比分析表（STK_InstantCostCompare）。

    对比即时成本与核算成本的差异。

    常用 filter_string：
    - 指定物料: "FMaterialId.FNumber='MAT001'"
    - 指定仓库: "FStockId.FNumber='WH01'"

    推荐 field_keys：
    FMaterialId.FNumber,FMaterialId.FName,FStockId.FName,FInstantCost,F核算成本,FDiffAmt

    Returns:
        str: JSON 格式的即时成本对比列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FMaterialId.FNumber,FMaterialId.FName,FStockId.FName,FInstantCost,FCostPrice,FDiffAmt"
        result = await _post("query", _query_payload(
            "STK_InstantCostCompare", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_cost_trend",
    annotations={"title": "成本价趋势分析", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_cost_trend(params: QueryInput) -> str:
    """查询成本价趋势分析表（STK_CostTrend）。

    分析物料成本价格的变化趋势。

    常用 filter_string：
    - 指定物料: "FMaterialId.FNumber='MAT001'"
    - 指定日期范围: "FDate>='2024-01-01' and FDate<='2024-12-31'"

    推荐 field_keys：
    FMaterialId.FNumber,FMaterialId.FName,FDate,FCostPrice,FPriceChange

    Returns:
        str: JSON 格式的成本价趋势列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FMaterialId.FNumber,FMaterialId.FName,FDate,FCostPrice,FPriceChange"
        result = await _post("query", _query_payload(
            "STK_CostTrend", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_finished_product_cost",
    annotations={"title": "完工入库成本查询", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_finished_product_cost(params: QueryInput) -> str:
    """查询完工入库产品成本（CB_FinishInCostQuery）。

    常用 filter_string：
    - 指定生产订单: "FMoBillNo='MO000001'"
    - 指定期间: "FYear=2024 and FPeriod='01'"

    推荐 field_keys：
    FMoBillNo,FMaterialId.FNumber,FMaterialId.FName,FFinishQty,FCostPrice,FCostAmt

    Returns:
        str: JSON 格式的完工成本列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FMoBillNo,FMaterialId.FNumber,FMaterialId.FName,FFinishQty,FCostPrice,FCostAmt"
        result = await _post("query", _query_payload(
            "CB_FinishInCostQuery", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_material_cost_usage",
    annotations={"title": "材料耗用成本查询", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_material_cost_usage(params: QueryInput) -> str:
    """查询生产材料耗用成本（CB_MaterialCostQuery）。

    常用 filter_string：
    - 指定生产订单: "FMoBillNo='MO000001'"
    - 指定物料: "FMaterialId.FNumber='MAT001'"

    推荐 field_keys：
    FMoBillNo,FMaterialId.FNumber,FMaterialId.FName,FConsumeQty,FCostPrice,FCostAmt

    Returns:
        str: JSON 格式的材料耗用成本列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FMoBillNo,FMaterialId.FNumber,FMaterialId.FName,FConsumeQty,FCostPrice,FCostAmt"
        result = await _post("query", _query_payload(
            "CB_MaterialCostQuery", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


# ─────────────────────────────────────────────
# 生产管理工具（生产订单/领料单/入库单）
# ─────────────────────────────────────────────

class ProductionOrderBillIdsInput(BillIdsInput):
    """生产订单单据ID输入模型"""
    pass


@mcp.tool(
    name="kingdee_query_production_orders",
    annotations={"title": "查询生产订单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_production_orders(params: QueryInput) -> str:
    """查询生产订单（PRD_MO）列表。

    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定日期: "FDate>='2024-01-01'"
    - 进行中: "FStatus='2'"  (1=计划,2=确认,3=投料,4=汇报,5=入库)
    - 指定物料: "FMaterialId.FNumber='MAT001'"

    推荐 field_keys：
    FID,FBillNo,FDate,FDocumentStatus,FMaterialId.FName,FQty,FPlanStartDate,FPlanFinishDate,FStatus

    Returns:
        str: JSON 格式的生产订单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FID,FBillNo,FDate,FDocumentStatus,FMaterialId.FNumber,FMaterialId.FName,FQty,FPlanStartDate,FPlanFinishDate,FStatus"
        result = await _post("query", _query_payload(
            "PRD_MO", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_production_pick_materials",
    annotations={"title": "查询生产领料单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_production_pick_materials(params: QueryInput) -> str:
    """查询生产领料单（PRD_PickMtrl）列表。

    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定生产订单: "FMoBillNo='MO000001'"
    - 指定仓库: "FStockId.FNumber='CK001'"

    推荐 field_keys：
    FID,FBillNo,FDate,FDocumentStatus,FMoBillNo,FMaterialId.FName,FPickQty,FStockId.FName

    Returns:
        str: JSON 格式的生产领料单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FID,FBillNo,FDate,FDocumentStatus,FMoBillNo,FMaterialId.FNumber,FMaterialId.FName,FPickQty,FStockId.FName"
        result = await _post("query", _query_payload(
            "PRD_PickMtrl", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_query_production_stock_in",
    annotations={"title": "查询生产入库单", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_query_production_stock_in(params: QueryInput) -> str:
    """查询生产入库单（PRD_Instock）列表。

    常用 filter_string：
    - 已审核: "FDocumentStatus='C'"
    - 指定生产订单: "FMoBillNo='MO000001'"
    - 指定仓库: "FStockId.FNumber='CK001'"

    推荐 field_keys：
    FID,FBillNo,FDate,FDocumentStatus,FMoBillNo,FMaterialId.FName,FInQty,FStockId.FName

    Returns:
        str: JSON 格式的生产入库单列表
    """
    try:
        fk = params.field_keys if params.field_keys != "FID,FBillNo,FDate,FDocumentStatus" \
            else "FID,FBillNo,FDate,FDocumentStatus,FMoBillNo,FMaterialId.FNumber,FMaterialId.FName,FInQty,FStockId.FName"
        result = await _post("query", _query_payload(
            "PRD_Instock", fk, params.filter_string,
            params.order_string, params.start_row, params.limit
        ))
        rows = _rows(result)
        return _fmt({"count": len(rows), "has_more": len(rows) == params.limit, "data": rows})
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="kingdee_view_production_order",
    annotations={"title": "查看生产订单详情", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False}
)
async def kingdee_view_production_order(params: ViewInput) -> str:
    """查看生产订单（PRD_MO）完整详情。

    必填参数：
    - form_id: "PRD_MO"
    - bill_id: 单据 FID 或 bill_no: 单据编号

    Returns:
        str: JSON 格式的生产订单完整数据
    """
    try:
        result = await _post("view", ["PRD_MO", params.to_view_payload()])
        return _fmt({"form_id": "PRD_MO", "data": result.get("Result", result)})
    except Exception as e:
        return _err(e)


class ProductionOrderSaveInput(SaveInput):
    """生产订单保存输入模型"""
    pass


@mcp.tool(
    name="kingdee_save_production_order",
    annotations={"title": "新建或修改生产订单", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_save_production_order(params: ProductionOrderSaveInput) -> str:
    """新建或修改生产订单（PRD_MO）。

    新建示例：
    {
      "FDate": "2024-01-15",
      "FMaterialId": {"FNumber": "MAT001"},
      "FQty": 100,
      "FPlanStartDate": "2024-01-20",
      "FPlanFinishDate": "2024-01-25"
    }

    Returns:
        str: JSON，含 FID 和 FBillNo
    """
    try:
        model = dict(params.model)
        model.setdefault("FID", 0)
        result = await _post_raw(
            "save", "PRD_MO", model,
            need_return_fields=["FID", "FBillNo"],
        )
        status_data = _result_status(result, "save")
        if status_data.get("success"):
            status_data["tip"] = "生产订单已保存为草稿，需要提交+审核后才能下推领料单"
        return _fmt(status_data)
    except Exception as e:
        return _err(e, op="save")


@mcp.tool(
    name="kingdee_submit_production_orders",
    annotations={"title": "提交生产订单", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_submit_production_orders(params: ProductionOrderBillIdsInput) -> str:
    """提交生产订单（PRD_MO）至审核队列。

    Returns:
        str: JSON，含 success / next_action / bill_ids
    """
    try:
        result = await _post_raw("submit", "PRD_MO", {"Ids": params.bill_ids})
        status_data = _result_status(result, "submit")
        if status_data.get("success"):
            status_data["next_action"] = "kingdee_audit_production_orders"
        return _fmt(status_data)
    except Exception as e:
        return _err(e, op="submit")


@mcp.tool(
    name="kingdee_audit_production_orders",
    annotations={"title": "审核生产订单", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_audit_production_orders(params: ProductionOrderBillIdsInput) -> str:
    """审核生产订单（PRD_MO）。

    Returns:
        str: JSON，含 success / bill_ids
    """
    try:
        result = await _post_raw("audit", "PRD_MO", {"Ids": params.bill_ids})
        return _fmt(_result_status(result, "audit"))
    except Exception as e:
        return _err(e, op="audit")


class ProductionPickPushInput(BaseModel):
    """生产订单下推领料单输入"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    bill_nos: List[str] = Field(description="源单生产订单编号列表")
    rule_id: Optional[str] = Field(default=None, description="转换规则ID")
    draft_on_fail: bool = Field(default=True)


@mcp.tool(
    name="kingdee_push_production_pick",
    annotations={"title": "生产订单下推领料单", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_push_production_pick(params: ProductionPickPushInput) -> str:
    """从生产订单下推生成生产领料单（PRD_PickMtrl）。

    Returns:
        str: JSON，含 success / target_bill_nos / next_action
    """
    try:
        result = await _post_raw(
            "push", "PRD_MO", {"Ids": params.bill_nos},
            target_form_id="PRD_PickMtrl",
            rule_id=params.rule_id,
            draft_on_fail=params.draft_on_fail,
        )
        status_data = _result_status(result, "push")
        if status_data.get("success"):
            status_data["next_action"] = "kingdee_submit_bills + kingdee_audit_bills"
            status_data["tip"] = "领料单审核时扣减即时库存"
        return _fmt(status_data)
    except Exception as e:
        return _err(e, op="push")


class ProductionStockInPushInput(BaseModel):
    """生产领料单下推入库输入"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    bill_nos: List[str] = Field(description="源单生产领料单编号列表")
    rule_id: Optional[str] = Field(default=None)
    draft_on_fail: bool = Field(default=True)


@mcp.tool(
    name="kingdee_push_production_stock_in",
    annotations={"title": "生产领料单下推入库单", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_push_production_stock_in(params: ProductionStockInPushInput) -> str:
    """从生产领料单下推生成生产入库单（PRD_Instock）。

    Returns:
        str: JSON，含 success / target_bill_nos / next_action
    """
    try:
        result = await _post_raw(
            "push", "PRD_PickMtrl", {"Ids": params.bill_nos},
            target_form_id="PRD_Instock",
            rule_id=params.rule_id,
            draft_on_fail=params.draft_on_fail,
        )
        status_data = _result_status(result, "push")
        if status_data.get("success"):
            status_data["next_action"] = "kingdee_submit_bills + kingdee_audit_bills"
            status_data["tip"] = "入库单审核时增加即时库存"
        return _fmt(status_data)
    except Exception as e:
        return _err(e, op="push")


# ─────────────────────────────────────────────
# 计划管理 + 生产汇报
# ─────────────────────────────────────────────

class MRPResultQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    filter_string: str = Field(default="", description="过滤条件，如 FMaterialId.FNumber='123'")
    top: int = Field(default=200, description="返回条数限制")
    orderby: str = Field(default="FCreateDate DESC", description="排序字段")


@mcp.tool(
    name="kingdee_query_mrp_result",
    annotations={"title": "MRP运算结果查询", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_query_mrp_result(params: MRPResultQueryInput) -> str:
    """查询 MRP 运算结果（PLAN_MRPResult）。

    来自销售订单/销售预测/库存不足等需求，经 MRP 运算生成的计划订单建议。
    可下推生成采购申请/生产订单。

    Returns:
        str: JSON 数组，每条含 FBillNo/FMaterialId/FSrcBillNo/FPurchaseQty 等字段。
    """
    try:
        result = await _post("query", "PLAN_MRPResult", [
            "PLAN_MRPResult",
            params.filter_string,
            params.top,
            params.orderby,
            "FDetailId,FPlanQty,FBillNo,FMaterialId,FUnitId,FPlanDate,FSupplyMrpRuleId,FMrpResultId,FIsExploit,FMoBillNo,FMoEntryId,FPOBillNo,FPOEntryId,FPRBillNo,FPREntryId,FSupplyRuleId,FSourceBillType,FSrcBillId,FSrcBillNo,FSrcBillEntryId,FSupplyRuleId,FSupplyDate,FSupplyOrgId,FSupplyOrgName,FCurrentSupState,FRequireOrgId,FRequireOrgName,FRequireDeptId,FCreatorId,FCreateDate,FModifierId,FModifyDate,FDocumentStatus,FDescription,Fmrpresultentry_l,F_RTV1_TEXT,F_RTV2_TEXT,F_RTV3_TEXT,F_RTV4_DEC,F_RTV5_DEC",
        ])
        return _fmt(result)
    except Exception as e:
        return _err(e, op="query")


class ProductionPlanQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    filter_string: str = Field(default="", description="过滤条件")
    top: int = Field(default=200, description="返回条数限制")
    orderby: str = Field(default="FCreateDate DESC", description="排序字段")


@mcp.tool(
    name="kingdee_query_production_plan",
    annotations={"title": "生产计划单查询", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_query_production_plan(params: ProductionPlanQueryInput) -> str:
    """查询生产计划单（PLAN_ProductionPlan）。

    生产计划单是 MRP 运算后手工调整的计划单据，可直接下推生成生产订单。

    Returns:
        str: JSON 数组。
    """
    try:
        result = await _post("query", "PLAN_ProductionPlan", [
            "PLAN_ProductionPlan",
            params.filter_string,
            params.top,
            params.orderby,
            "FBillNo,FMaterialId,FPlanQty,FPlanStartDate,FPlanEndDate,FStatus,FWorkShopId,FDocumentStatus",
        ])
        return _fmt(result)
    except Exception as e:
        return _err(e, op="query")


class ProductionReportQueryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    filter_string: str = Field(default="", description="过滤条件，如 FMaterialId.FNumber='123'")
    top: int = Field(default=200, description="返回条数限制")
    orderby: str = Field(default="FCreateDate DESC", description="排序字段")


@mcp.tool(
    name="kingdee_query_production_report",
    annotations={"title": "生产汇报单查询", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False}
)
async def kingdee_query_production_report(params: ProductionReportQueryInput) -> str:
    """查询生产汇报单（PRD_MOReport）。

    生产汇报记录工序完成数量/工时/良品率等信息，是生产入库的提前工序。

    Returns:
        str: JSON 数组，含 FBillNo/FMOId/FMaterialId/FReportQty/FHourQty 等。
    """
    try:
        result = await _post("query", "PRD_MOReport", [
            "PRD_MOReport",
            params.filter_string,
            params.top,
            params.orderby,
            "FBillNo,FMOId,FMOBillNo,FMaterialId,FMaterialName,FReportQty,FUnitId,FFinishedQty,FScrapQty,FHourQty,FWorkStationId,FWorkGroupId,FProcessId,FDocumentStatus,FCreateDate",
        ])
        return _fmt(result)
    except Exception as e:
        return _err(e, op="query")


# ─────────────────────────────────────────────
# 入口函数
# ─────────────────────────────────────────────
def _run_check() -> int:
    """跑一次登录验证当前环境变量配置是否正确，返回 exit code"""
    import asyncio

    required = {
        "KINGDEE_SERVER_URL": SERVER_URL,
        "KINGDEE_ACCT_ID":    ACCT_ID,
        "KINGDEE_USERNAME":   USERNAME,
        "KINGDEE_APP_ID":     APP_ID,
        "KINGDEE_APP_SEC":    APP_SEC,
    }
    missing = [k for k, v in required.items() if not v or v == "http://your-server/k3cloud/"]
    if missing:
        print("[FAIL] 缺少环境变量: " + ", ".join(missing))
        return 1

    print(f"[INFO] 服务器: {SERVER_URL}")
    print(f"[INFO] 账套: {ACCT_ID}  用户: {USERNAME}  AppID: {APP_ID[:8]}...")
    print("[INFO] 正在尝试登录金蝶...")
    try:
        sid = asyncio.run(_login())
        print(f"[OK] 登录成功，SessionId: {sid[:12]}...")
        print("[OK] 配置正确，可在 MCP 客户端中使用。")
        return 0
    except httpx.HTTPError as e:
        print(f"[FAIL] 网络错误: {e}")
        print("       请检查 KINGDEE_SERVER_URL 是否可访问、是否含 /k3cloud/ 后缀。")
        return 2
    except RuntimeError as e:
        print(f"[FAIL] {e}")
        print("       请检查 ACCT_ID / USERNAME / APP_ID / APP_SEC 是否正确，集成用户是否启用。")
        return 3
    except Exception as e:
        print(f"[FAIL] 未知错误: {type(e).__name__}: {e}")
        return 4


def main():
    """MCP Server 入口点"""
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in ("--check", "check"):
        sys.exit(_run_check())
    mcp.run()


if __name__ == "__main__":
    main()
