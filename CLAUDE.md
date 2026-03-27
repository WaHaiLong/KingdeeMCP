# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install in development mode
pip install -e .

# Run the MCP server directly
kingdee-mcp

# Run with uvx (no install needed)
uvx kingdee-mcp

# Build distribution package
pip install hatchling
python -m hatchling build

# Install with all deps
pip install "mcp[cli]>=1.0.0" httpx pydantic
```

Run tests:
```bash
# Unit + mock tests (no Kingdee server required)
python -m pytest tests/ -v

# Integration tests (requires Kingdee server + env vars)
KINGDEE_SERVER_URL=http://your-server/k3cloud/ \
KINGDEE_ACCT_ID=... KINGDEE_USERNAME=... \
KINGDEE_APP_ID=... KINGDEE_APP_SEC=... \
python -m pytest tests/test_integration.py -v
```

## Architecture

This is a single-file MCP Server (`src/kingdee_mcp/server.py`) that bridges AI clients to Kingdee Cloud K/3 ERP via its WebAPI.

### Request Flow

1. AI client calls a tool → FastMCP dispatches to the decorated async function
2. Function calls `_post(ep_key, payload)` with a `[form_id, {params}]` list
3. `_post()` checks the global `_session_id` cache; calls `_login()` if absent
4. On 401 or session-expired response, auto re-logins and retries once
5. All tools return JSON strings (success or error message from `_err()`)

### Key Internals

- **`_EP` dict** — maps short names (`"query"`, `"save"`, etc.) to full Kingdee WebAPI endpoint paths
- **`_session_id` global** — cached session cookie (`kdservice-sessionid`) from `LoginByAppSecret`
- **`FORM_CATALOG` dict** — maps `form_id` → `{name, alias[], fields}` used by `kingdee_list_forms` and `kingdee_get_fields` to help the AI discover form IDs without hitting the API
- **Pydantic input models** — each tool has a dedicated model (`QueryInput`, `SaveInput`, `BillIdsInput`, etc.) with `extra="forbid"` for strict validation

### Tool Categories

| Category | Tools |
|----------|-------|
| Metadata | `kingdee_list_forms`, `kingdee_get_fields` |
| Read-only queries | `kingdee_query_bills`, `kingdee_view_bill`, `kingdee_query_purchase_orders`, `kingdee_query_sale_orders`, `kingdee_query_stock_bills`, `kingdee_query_inventory`, `kingdee_query_materials`, `kingdee_query_partners` |
| Write operations | `kingdee_save_bill`, `kingdee_submit_bills`, `kingdee_audit_bills`, `kingdee_unaudit_bills`, `kingdee_delete_bills`, `kingdee_push_bill` |
| Workflow | `kingdee_query_pending_approvals`, `kingdee_query_workflow_status`, `kingdee_workflow_approve`, `kingdee_query_expense_reimburse` |
| SQL Server introspection | `kingdee_discover_tables`, `kingdee_discover_columns`, `kingdee_describe_table`, `kingdee_discover_metadata_candidates` |

### Environment Variables (required at runtime)

| Variable | Description |
|----------|-------------|
| `KINGDEE_SERVER_URL` | Server URL ending in `/k3cloud/` |
| `KINGDEE_ACCT_ID` | Account set ID |
| `KINGDEE_USERNAME` | Integration user name |
| `KINGDEE_APP_ID` | App ID from Kingdee admin |
| `KINGDEE_APP_SEC` | App Secret from Kingdee admin |
| `MCP_SQLSERVER_HOST` | SQL Server host (optional, for DB introspection) |
| `MCP_SQLSERVER_PORT` | SQL Server port (default 1433) |
| `MCP_SQLSERVER_DATABASE` | Database name |
| `MCP_SQLSERVER_USER` | SQL Server user (read-only recommended) |
| `MCP_SQLSERVER_PASSWORD` | SQL Server password |

### GitHub Pages (`docs/`)

The website at `https://wahailong.github.io/KingdeeMCP/` is a single static HTML file (`docs/index.html`). The deploy workflow (`.github/workflows/deploy-pages.yml`) triggers on push to `main` branch.

### Examples (`examples/`)

Business scenario examples showing how to use each tool. See `examples/README.md` for the full list. Useful as reference when helping users with Kingdee MCP queries.

