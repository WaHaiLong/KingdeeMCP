# 金蝶云星空 MCP Server

让 Claude 直接操作金蝶云星空私有云，支持供应链、库存、基础资料模块。

## 支持的 Tools（13个）

| Tool 名称 | 功能 |
|---|---|
| kingdee_query_bills | 通用单据查询（任意 form_id）|
| kingdee_view_bill | 查看单据完整详情 |
| kingdee_query_purchase_orders | 查询采购订单 |
| kingdee_query_sale_orders | 查询销售订单 |
| kingdee_query_stock_bills | 查询出入库单据 |
| kingdee_query_inventory | 查询即时库存 |
| kingdee_query_materials | 查询物料档案 |
| kingdee_query_partners | 查询客户/供应商 |
| kingdee_save_bill | 新建或修改单据 |
| kingdee_submit_bills | 提交单据 |
| kingdee_audit_bills | 审核单据 |
| kingdee_unaudit_bills | 反审核单据 |
| kingdee_delete_bills | 删除单据 |

---

## 安装步骤

### 1. 克隆项目
```bash
cd ~/projects
# 把项目文件夹放到这里
cd kingdee-mcp
```

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置连接信息
```bash
cp .env.example .env
# 编辑 .env 填入你的金蝶连接信息
```

### 4. 金蝶后台授权配置
在金蝶云星空中：
1. 进入 **系统管理 → 第三方系统登录授权 → 新增**
2. 新建一个集成用户（不要用 Administrator）
3. 生成应用ID和应用密钥
4. 将这4个信息填入 `.env` 文件

### 5. 在 Claude Desktop 中注册
编辑 `claude_desktop_config.json`（Windows 路径：`%APPDATA%\Claude\claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "kingdee": {
      "command": "python",
      "args": ["C:/projects/kingdee-mcp/server.py"],
      "env": {
        "KINGDEE_SERVER_URL": "http://your-server/k3cloud/",
        "KINGDEE_ACCT_ID": "your_acct_id",
        "KINGDEE_USERNAME": "API集成",
        "KINGDEE_APP_ID": "your_app_id",
        "KINGDEE_APP_SEC": "your_app_secret"
      }
    }
  }
}
```

### 6. 重启 Claude Desktop

---

## 使用示例

注册成功后，可以直接对 Claude 说：

- "查询最近20条已审核的采购订单"
- "查一下物料编码 MAT001 的即时库存"
- "查询客户编码 C001 的所有销售订单"
- "帮我新建一张采购订单，供应商S001，物料MAT001，数量100，单价10.5"
- "审核这几张采购入库单：12345, 12346"

---

## 常见问题

**Q: 提示认证失败**
检查 AppID / AppSec 是否正确，集成用户是否有对应模块权限。

**Q: 连接超时**
检查 KINGDEE_SERVER_URL 是否正确，服务器是否在同一局域网内。

**Q: 查询结果为空**
检查 filter_string 过滤条件语法，金蝶使用类 SQL 语法。
