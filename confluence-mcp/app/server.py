import truststore
truststore.inject_into_ssl()  # use Windows cert store (handles CIBC corporate proxy)

from mcp.server.fastmcp import FastMCP
from . import confluence

mcp = FastMCP("confluence-mcp", stateless_http=True)


@mcp.tool()
async def confluence_search(query: str, limit: int = 5) -> list[dict]:
    """Search Confluence pages by free-text query. Returns id, title, url, excerpt."""
    return await confluence.search(query, limit)


@mcp.tool()
async def confluence_get_page(page_id: str) -> dict:
    """Fetch a single Confluence page by ID. Returns title, url, body as markdown."""
    return await confluence.get_page(page_id)


@mcp.tool()
async def confluence_list_spaces() -> list[dict]:
    """List all accessible Confluence spaces. Returns key and name for each."""
    return await confluence.list_spaces()


# ASGI app exposing the MCP endpoint at /mcp
app = mcp.streamable_http_app()
