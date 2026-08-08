# 更新日志 (Changelog)

本项目所有重要变更都会记录在此文件。

格式参考 [Keep a Changelog](https://keepachangelog.com/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> 当前 PyPI 版本：`0.2.1`（见 `pyproject.toml`）。本文件按功能里程碑汇总，未单独打 git tag。

---

## [Unreleased]

### Fixed（修复）

- **批量 Submit/Audit/Unaudit/Delete 不再静默丢单**（issue #8）：`_post_raw` 遇到列表形式的 `Ids` 时原本只取首个（`ids[0]`），其余 ID **被静默丢弃且接口仍返回 `success: true`**。用户批量反审核 11 张单据，实际只有 1 张生效。现改为按金蝶 WebAPI 约定逗号拼接（`{"Ids":"100,101,102"}`，与 `CancelAssign` / `ExecuteOperation` 同一约定），并抽出纯函数 `_normalize_ids()`（自动去空白、去重保序，空 ID 显式报错而非发空请求）。
  - `kingdee_submit_bills` / `kingdee_audit_bills` / `kingdee_unaudit_bills` / `kingdee_delete_bills` 此前已改为逐张调用绕开了该问题，但**根因未除**：`kingdee_submit_production_orders` / `kingdee_audit_production_orders` 仍在直接传列表，批量提交生产订单时同样只有首张生效。本次从根上修掉。
- **批量操作新增「提交数 vs 成功数」对账**（issue #8 的另一半）：`_result_status()` 原先只看金蝶返回的 `IsSuccess`，从不核对实际生效数量 —— 金蝶少处理了单据仍会报成功。现新增可选参数 `requested_ids`，传入后与 `SuccessEntitys` 对账，发现漏单则把 `success` 置为 `False` 并列出 `missing_ids`。不传该参数时行为完全不变，老调用方零影响。

### Changed（变更）

- **CI 补跑回归测试**：`harness-check.yml` 此前只跑 `tests/test_server.py`，导致 issue #13 的表名一致性回归测试（`test_db_tables_consistency.py`）虽已入库却从未在 CI 中执行 —— 表名被改回去 CI 依然是绿的。现新增独立步骤，显式运行全部「对应真实用户 issue」的回归测试。

### Added（新增）

- **远程传输支持（HTTP / SSE / Streamable HTTP）**：`main()` 新增 `--transport`（stdio/sse/streamable-http，默认 stdio）、`--host`、`--port` 参数，并支持同名环境变量 `KINGDEE_MCP_TRANSPORT` / `KINGDEE_MCP_HOST` / `KINGDEE_MCP_PORT`。现在可将服务以 SSE（`/sse`）或 Streamable HTTP（`/mcp`）模式运行，便于部署到服务器或网关平台远程调用、免客户端安装。兼容老版本 mcp（<1.9 不支持 streamable-http 时自动回退 sse）。

---

## [0.2.1] - 2026-08-05

### Fixed（修复 · 文档）

- **修正改用账号密码登录的原因说明**：README「从 0.1.0 升级的破坏性变更」与 `server.py` `_login` docstring 原写为「为避免第三方应用授权的 APP 白名单限制、公有云/私有云通用」，该原因有误。正确原因：账号密码(ValidateUser) 以真实用户身份执行 WebAPI、携带该用户自身业务权限（含数据权限控制）；第三方应用授权(LoginByAppSecret) 以应用身份登录、不携带真实用户权限，报表等依赖数据权限的查询会受应用授权范围限制。无功能/行为变更。

---

## [0.2.0] - 2026-08-05

### Changed（变更）

- **版本对齐与重新发版**：本地源码自 2026-07-19 起已包含 86 工具、账号密码登录、SQL Server 探查等大量更新，但 PyPI 上仍停留在 2026-03-25 发布的旧 `0.1.0`（仅 13 工具 + AppSecret 登录）。本版将 PyPI 包与源码对齐，统一为 `0.2.0`。
- **README / 文档同步**：PyPI 展示的 README 已更新为 86 工具 + 账号密码登录的说明（此前 PyPI 长期展示旧版文档）。

### Added（新增 · 相对 PyPI 旧 0.1.0）

- 86 个工具（生产 / 成本 / 资产 / 审计 / 采购 / 销售 / 库存 / 工作流 / 元数据 / 系统 / 统计等 13 大业务域）。
- 4 个 SQL Server 探查工具（`kingdee_discover_tables` / `kingdee_discover_columns` / `kingdee_describe_table` / `kingdee_discover_metadata_candidates`），需配置 `MCP_SQLSERVER_*`。
- 元数据动态查询（`get_bill_template` / `validate_bill` / `refresh_metadata`），元数据本地缓存。
- MCP 使用日志系统、错误自描述、强制 HTTP/1.1 解决金蝶 WebAPI 偶发 502。
- **财务报表查询工具 `kingdee_query_report`**：通过专用 `GetSysReportData`（KDSReportAPIService）端点查询总账/财务报表，与单据查询（ExecuteBillQuery）分属不同服务。已实测确认科目余额表 `GL_RPT_AccountBalance`、总账账龄分析表 `GL_AgingSchedule`（无 `RPT_` 前缀）；其余报表 formId 待逐张查证。内层过滤参数（账簿/年度/期间/科目等）由调用方按账套透传，避免臆造字段名。

### Breaking（破坏性变更）

- **登录方式变更**：移除第三方应用授权登录（`LoginByAppSecret`），改为仅账号密码（`ValidateUser`）。旧环境变量 `KINGDEE_APP_ID` / `KINGDEE_APP_SEC` **已失效**，须改用 `KINGDEE_PASSWORD`。详见 README「从 0.1.0 升级的破坏性变更」。

### Fixed（修复 · 文档）

- README「常见问题」新增 `uvx` 启动报 `No module named 'mcp.server.fastmcp'` 的排查（清缓存或改用 `pip install` + `python -m kingdee_mcp.server`）。

---

## [0.1.0] - 2026-07-19

### Added（新增）

- **13 大业务域、共 86 个工具**，覆盖生产制造、成本核算、固定资产、审计合规、采购、销售、库存、工作流审批、基础资料、元数据探查、系统查询等。
- **生产制造模块**：生产订单查询/保存/提交/审核、MRP 运算结果、生产计划、生产汇报、生产入库、生产领料下推（`kingdee_query_production_*`、`kingdee_save_production_order`、`kingdee_push_production_*` 等 12 个）。
- **成本核算模块**：材料成本、成本计算、成本趋势、实际 vs 标准成本对比、完工产品成本、成本调整单等（`kingdee_query_material_cost`、`kingdee_query_cost_calculation`、`kingdee_save_cost_adjustment` 等 12 个）。
- **固定资产模块**：资产卡片、资产折旧、资产盘点、资产调拨、资产新增（`kingdee_query_fixed_asset`、`kingdee_save_asset` 等 6 个）。
- **审计合规模块**：操作日志、变更日志、审核日志、复合「新建并审核」「下推并审核」工作流（`kingdee_query_operation_logs`、`kingdee_query_change_log`、`kingdee_create_and_audit`、`kingdee_push_and_audit` 等 7 个）。
- **元数据动态查询**：`kingdee_get_bill_template`（取已验证单据骨架）、`kingdee_validate_bill`（保存前校验，不真正落库）、`kingdee_refresh_metadata`（强制刷新），元数据落盘缓存到 `~/.workbuddy/kingdee_metadata_cache/`。
- **SQL Server 探查工具 4 个**：`kingdee_discover_tables`、`kingdee_discover_columns`、`kingdee_describe_table`、`kingdee_discover_metadata_candidates`（配置 `MCP_SQLSERVER_*` 环境变量后可用）。
- **MCP 使用日志系统**：记录工具调用，便于审计与排查。
- **权限架构设计方案**文档（`docs/permission-architecture.md`）。
- **TEST_GUIDE 与生产工作流 e2e** 测试，回归网覆盖核心链路。

### Changed（变更）

- **登录方式改为仅账号密码（ValidateUser）**，移除第三方应用授权（原 `LoginByAppSecret`）。配置只需 `KINGDEE_SERVER_URL`、`KINGDEE_ACCT_ID`、`KINGDEE_USERNAME`、`KINGDEE_PASSWORD` 四项，**不再需要 AppID / AppSecret**。
- `kingdee_view_bill` 返回结果精简，只保留常用字段，降低 token 消耗。
- `kingdee_query_bills` 等查询类工具的过滤与返回结构优化。
- 批量操作（提交/审核/反审核/删除）真正批量化，减少循环请求。
- 错误自描述：接口失败时返回更可读的中文错误，便于 AI 与用户定位。
- 强制使用 HTTP/1.1 解决金蝶 WebAPI 偶发 502 问题。
- 文档/示例/脚本/测试整体同步。

### Fixed（修复）

- **销售报价单（SAL_Quotation）保存报"含税单价不能小于等于0"的真正根因 = 字段顺序**：本二开账套金蝶 Save 对字段顺序敏感，`FQUOTATIONFIN`（财务信息，含结算币别/含税标志）必须排在 `FQUOTATIONENTRY`（分录）之前，否则分录单价被算成 0。`kingdee_save_bill` 新增防御性排序（所有非 ENTRY 键统一前置），`BILL_TEMPLATES` 补 `FQUOTATIONFIN` 并置于 ENTRY 之前。
- 修正 `kingdee_push_bill` API 格式、`_post_raw` 入参与生产下推（`push_production`）参数。
- 补全若干缺失函数，修复批量操作的一致性。

### Removed（移除）

- 第三方应用授权登录（`LoginByAppSecret`）及相关 `APP_ID` / `APP_SEC` 环境变量、配置项。

---

## 历史提交摘要（按时间倒序，供溯源）

| 提交 | 说明 |
|------|------|
| `f58c2a7` | fix: 销售报价单 Save 字段顺序校正 + 新增 API 中心快照 |
| `c3fbaf5` | feat: 登录改为仅账号密码(ValidateUser)，移除第三方应用授权 |
| `a5b17e5` | chore: 忽略运行时日志/工具缓存/记忆目录/临时文件 |
| `6145af1` | test: 新增 TEST_GUIDE 和生产工作流 e2e |
| `a61d845` | chore: 同步文档/示例/脚本/测试 |
| `5c742a0` | feat: 元数据动态查询 + view 结果精简 |
| `6b7b58d` | docs: 添加权限架构设计方案 |
| `529a55e` | feat: 添加 MCP 使用日志系统 |
| `5bbc744` | fix: 批量操作真批量化 + 补全缺失函数 + 修正 push_production 参数 |
| `04d4eba` | feat: 新增 MRP/生产计划/生产汇报查询工具 |
| `96f7f93` | feat: 新增审计合规模块 API |
| `354e339` | feat: 新增生产、成本、资产管理等模块 API |
| `e034152` | feat: 复合工作流工具 + 错误自描述 + e2e 回归网 |
| `6b754c3` | fix: 强制使用 HTTP/1.1 解决金蝶 WebAPI 502 问题 |
| `30b2a19` | feat: 新增 4 个 SQL Server 探查工具 |

完整历史见 [GitHub Commits](https://github.com/WaHaiLong/KingdeeMCP/commits/main)。
