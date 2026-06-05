# CIBC AI DevKit — Hackathon Handoff

**Demo deadline:** June 5 (tomorrow AM). 2 developers in parallel.

This doc tells the `snow-mcp` developer (and their AI assistant) **exactly what already exists**, **what conventions to mirror**, and **how the two servers meet** in Copilot Studio.

---

## 1. Architecture (locked — no changes)

```
┌────────────────────────┐
│  Azure Copilot Studio  │   (no-code agent — Layer 1)
└───────────┬────────────┘
            │ HTTPS / MCP (Streamable HTTP) via ngrok tunnels
   ┌────────┴────────┐
   ▼                 ▼
┌──────────────┐  ┌──────────────┐
│ confluence-  │  │ snow-mcp     │   (Layer 2 — local Python)
│ mcp  ✅ DONE │  │   ❌ TODO    │
│ :8001/mcp    │  │ :8002/mcp    │
└──────┬───────┘  └──────┬───────┘
       │                 │
       ▼                 ▼
┌──────────────┐  ┌──────────────┐
│ Confluence   │  │ ServiceNow   │   (Layer 3 — external SaaS)
│ Cloud (free) │  │ PDI (free)   │
└──────────────┘  └──────────────┘
```

**Demo narrative (90 seconds):**
1. User: *"I'm joining Project APEX. What access do I need?"*
2. Agent calls `confluence_search("Project APEX")` → finds page
3. Agent calls `confluence_get_page(page_id)` → reads required access list
4. Agent asks user for name + business justification
5. Agent calls `snow_create_request(...)` once per access item (parallel)
6. Agent returns: *"Created REQ0010001, REQ0010002, REQ0010003."*

---

## 2. Repo layout

```
MCP Server for Hackathon/
├── HANDOFF.md                  ← you are here
├── confluence-mcp/             ← ✅ done (Rayan)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py           ← env loading
│   │   ├── confluence.py       ← httpx client for Atlassian REST
│   │   └── server.py           ← FastMCP server + tool definitions
│   ├── .env.example
│   ├── .gitignore
│   ├── requirements.txt
│   └── README.md
└── snow-mcp/                   ← ❌ build this — mirror the layout above
    ├── app/
    │   ├── __init__.py
    │   ├── config.py
    │   ├── snow.py             ← httpx client for ServiceNow Table API
    │   └── server.py           ← FastMCP server + tool definitions
    ├── .env.example
    ├── .gitignore
    ├── requirements.txt
    └── README.md
```

**Why two top-level folders (not a monorepo with shared deps):** zero coupling, each dev owns their venv, no merge conflicts on `requirements.txt`.

---

## 3. Conventions to mirror exactly

These match what `confluence-mcp` already does. Please follow them so the demo "just works".

### 3.1 Stack
- Python 3.11+ (Rayan is on 3.13, fine)
- `mcp[cli]>=1.2.0` — official MCP Python SDK
- `httpx>=0.27` — async HTTP
- `python-dotenv` — load `.env`
- `uvicorn>=0.30` — ASGI server
- **`truststore>=0.9`** — REQUIRED on CIBC laptops, otherwise SSL fails on the corporate proxy

### 3.2 Transport
**Streamable HTTP** (NOT stdio). Copilot Studio's MCP connector needs HTTP.

In `server.py`:
```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("snow-mcp", stateless_http=True)
# ... tool definitions ...
app = mcp.streamable_http_app()   # ASGI app exposed at /mcp
```

### 3.3 Corporate SSL fix (REQUIRED)
First two lines of `server.py`, before any other import that uses SSL:
```python
import truststore
truststore.inject_into_ssl()  # use Windows cert store (handles CIBC corporate proxy)
```

### 3.4 Port assignments
| Server          | Port  |
|-----------------|-------|
| confluence-mcp  | 8001  |
| **snow-mcp**    | **8002** |

### 3.5 Run command
```powershell
uvicorn app.server:app --port 8002
```
Endpoint will be `http://localhost:8002/mcp`.

### 3.6 `.env` format
- No angle brackets `< >`, no quotes, no spaces around `=`
- Committed file is `.env.example` (placeholders only); real `.env` is gitignored

### 3.7 Tool naming
Prefix every tool with the server name to avoid collisions in Copilot Studio:
- ✅ `snow_create_request`, `snow_get_request`
- ❌ `create_request`

### 3.8 Tool return shapes
Return plain `dict` / `list[dict]` from tool functions — FastMCP serializes to JSON automatically. Keep keys short and snake_case. Example from `confluence-mcp`:
```python
{"id": "98639", "title": "Project APEX...", "url": "...", "body_markdown": "..."}
```

---

## 4. Tools `snow-mcp` should expose (suggested)

Minimum for the demo:

| Tool | Inputs | Returns | Purpose |
|------|--------|---------|---------|
| `snow_create_request` | `short_description: str`, `description: str`, `requested_for: str` (user sys_id or user_name), `category: str = "access"` | `{number, sys_id, state, url}` | Creates one record in `sc_request` (or `incident` if simpler for the PDI) |
| `snow_get_request` | `number: str` (e.g. `REQ0010001`) | `{number, state, opened_at, short_description}` | Verify ticket after creation |
| `snow_list_groups` *(nice-to-have)* | `query: str = ""` | `[{name, sys_id}]` | Lets the agent map "Databricks access" → a real `sys_user_group` |

**ServiceNow REST endpoint pattern (Table API):**
```
POST https://<instance>.service-now.com/api/now/table/<table_name>
Authorization: Basic base64(user:pass)
Content-Type: application/json
```

For a hackathon PDI, the simplest table to write to is `incident` (always exists, no catalog setup). If you want it to look more realistic, use `sc_request` or `sc_req_item`. Pick one and we'll match the agent prompt to it.

---

## 5. `.env` contents for snow-mcp

```
SNOW_INSTANCE_URL=https://devXXXXXX.service-now.com
SNOW_USERNAME=admin
SNOW_PASSWORD=<the PDI admin password>
SNOW_TABLE=incident
```

---

## 6. What's already verified working in `confluence-mcp`

| Check | Status |
|------|--------|
| Deps install on Win 11 + Python 3.13 | ✅ |
| CIBC corporate SSL proxy via `truststore` | ✅ |
| Atlassian Basic auth (email + API token) | ✅ |
| Direct REST call to fetch page by ID | ✅ |
| Uvicorn boots, `/mcp` endpoint live | ✅ |
| MCP client lists 3 tools and calls them | ✅ |

The same checks should pass for `snow-mcp` against the PDI before we wire Copilot Studio.

---

## 7. How we'll merge

1. Push to a single GitHub repo with both `confluence-mcp/` and `snow-mcp/` as siblings.
2. Each dev has their own `.env` (gitignored).
3. On demo day: each dev runs `uvicorn` in their own terminal, then we run **two `ngrok` tunnels** (one per port) and paste both URLs into Copilot Studio as separate MCP connectors.

---

## 8. Quick snippet for the snow-mcp dev's AI assistant

If you're a coding assistant reading this: scaffold `snow-mcp/` to mirror `confluence-mcp/` exactly, using the conventions in §3, the tools in §4, and the `.env` keys in §5. Do **not** use stdio transport, do **not** skip the `truststore` lines, and use port **8002**. Keep it under ~150 lines total. Do not add tests, CI, Docker, or extra abstractions — hackathon scope is locked.
