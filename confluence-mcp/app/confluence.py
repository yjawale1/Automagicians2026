import httpx
from markdownify import markdownify
from .config import BASE_URL, EMAIL, API_TOKEN, SPACE_KEY

_auth = (EMAIL, API_TOKEN)
_headers = {"Accept": "application/json"}


def _page_url(page_id: str, webui: str | None = None) -> str:
    if webui:
        return f"{BASE_URL}{webui}"
    return f"{BASE_URL}/pages/viewpage.action?pageId={page_id}"


async def search(query: str, limit: int = 5) -> list[dict]:
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
            "title": item["title"],
            "url": _page_url(item["id"], item.get("_links", {}).get("webui")),
            "excerpt": item.get("excerpt", ""),
        }
        for item in results
    ]


async def get_page(page_id: str) -> dict:
    params = {"expand": "body.storage,_links"}
    async with httpx.AsyncClient(auth=_auth, headers=_headers, timeout=15) as c:
        r = await c.get(f"{BASE_URL}/rest/api/content/{page_id}", params=params)
        r.raise_for_status()
        page = r.json()
    html = page.get("body", {}).get("storage", {}).get("value", "")
    return {
        "id": page["id"],
        "title": page["title"],
        "url": _page_url(page["id"], page.get("_links", {}).get("webui")),
        "body_markdown": markdownify(html, heading_style="ATX").strip(),
    }


async def list_spaces() -> list[dict]:
    async with httpx.AsyncClient(auth=_auth, headers=_headers, timeout=15) as c:
        r = await c.get(f"{BASE_URL}/rest/api/space", params={"limit": 50})
        r.raise_for_status()
        results = r.json().get("results", [])
    return [{"key": s["key"], "name": s["name"]} for s in results]
