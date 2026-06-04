# confluence_mcp.py
import os
import logging
from typing import Any, Dict
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx
from markdownify import markdownify

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("confluence-mcp")

BASE_URL = os.environ.get("CONFLUENCE_BASE_URL", "").rstrip("/")
EMAIL = os.environ.get("CONFLUENCE_EMAIL")
API_TOKEN = os.environ.get("CONFLUENCE_API_TOKEN")
SPACE_KEY = os.environ.get("CONFLUENCE_SPACE_KEY") or None

if not (BASE_URL and EMAIL and API_TOKEN):
    raise RuntimeError("Set CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN in .env")

_auth = (EMAIL, API_TOKEN)
_headers = {"Accept": "application/json"}


def _page_url(page_id: str, webui: str | None = None) -> str:
    if webui:
        return f"{BASE_URL}{webui}"
    return f"{BASE_URL}/pages/viewpage.action?pageId={page_id}"


async def _search(query: str, limit: int = 5):
    cql = f'text ~ "{query}" AND type = page'
    if SPACE_KEY:
        cql += f' AND space.key = "{SPACE_KEY}"'
    params = {"cql": cql, "limit": limit, "expand": "content"}
    async with httpx.AsyncClient(auth=_auth, headers=_headers, timeout=15) as c:
        r = await c.get(f"{BASE_URL}/rest/api/content/search", params=params)
        r.raise_for_status()
        results = r.json().get("results", [])
    return [
        {
            "id": item["id"],
            "title": item.get("title"),
            "url": _page_url(item["id"], item.get("_links", {}).get("webui")),
            "excerpt": item.get("excerpt", ""),
        }
        for item in results
    ]


async def _get_page(page_id: str):
    params = {"expand": "body.storage,_links"}
    async with httpx.AsyncClient(auth=_auth, headers=_headers, timeout=15) as c:
        r = await c.get(f"{BASE_URL}/rest/api/content/{page_id}", params=params)
        r.raise_for_status()
        page = r.json()
    html = page.get("body", {}).get("storage", {}).get("value", "")
    return {
        "id": page.get("id"),
        "title": page.get("title"),
        "url": _page_url(page.get("id"), page.get("_links", {}).get("webui")),
        "body_markdown": markdownify(html, heading_style="ATX").strip(),
    }


async def _list_spaces():
    async with httpx.AsyncClient(auth=_auth, headers=_headers, timeout=15) as c:
        r = await c.get(f"{BASE_URL}/rest/api/space", params={"limit": 50})
        r.raise_for_status()
        results = r.json().get("results", [])
    return [{"key": s["key"], "name": s["name"]} for s in results]


app = FastAPI(title="confluence-mcp")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def mk_response(req_id, result=None, error=None):
    msg = {"jsonrpc": "2.0"}
    if req_id is not None:
        msg["id"] = req_id
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    return msg


@app.post("/")
async def rpc(request: Request):
    body = await request.json()
    log.info("Incoming: %s", body)
    method = body.get("method")
    req_id = body.get("id")
    try:
        if method == "initialize":
            res = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "confluence-mcp", "version": "1.0.0"},
            }
            return mk_response(req_id, res)

        if method == "tools/list":
            tools = [
                {
                    "name": "confluence_search",
                    "description": "Search Confluence pages by free-text query",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                        "required": ["query"],
                    },
                },
                {
                    "name": "confluence_get_page",
                    "description": "Fetch a Confluence page by ID",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"page_id": {"type": "string"}},
                        "required": ["page_id"],
                    },
                },
                {
                    "name": "confluence_list_spaces",
                    "description": "List accessible Confluence spaces",
                    "inputSchema": {"type": "object"},
                },
            ]
            return mk_response(req_id, {"tools": tools})

        if method == "tools/call":
            params = body.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name == "confluence_search":
                result = await _search(arguments.get("query", ""), limit=arguments.get("limit", 5))
            elif name == "confluence_get_page":
                result = await _get_page(arguments["page_id"])
            elif name == "confluence_list_spaces":
                result = await _list_spaces()
            else:
                raise ValueError(f"Unknown tool: {name}")
            return mk_response(req_id, {"content": [{"type": "json", "value": result}]})

        # notifications (no response required)
        if req_id is None:
            return {}
        return mk_response(req_id, None, {"code": -32601, "message": "Unknown method"})
    except Exception as e:
        log.exception("RPC error")
        return mk_response(req_id, None, {"code": -32603, "message": str(e)})


@app.get("/health")
async def health():
    return {"status": "ok"}