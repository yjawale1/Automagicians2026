# confluence-mcp

Read-only MCP server exposing Confluence Cloud to the CIBC AI DevKit agent
(Copilot Studio). Part of a 3-layer hackathon demo.

## Tools

| Tool | Purpose |
|------|---------|
| `confluence_search(query, limit=5)` | Free-text search across pages |
| `confluence_get_page(page_id)` | Fetch one page; body returned as markdown |
| `confluence_list_spaces()` | List accessible spaces |

## Setup

```powershell
cd confluence-mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# edit .env with your Confluence URL, email, and API token
```

Create an Atlassian API token at <https://id.atlassian.com/manage-profile/security/api-tokens>.

## Run locally

```powershell
uvicorn app.server:app --port 8001
```

MCP endpoint: `http://localhost:8001/mcp`

## Expose to Copilot Studio

Copilot Studio needs a public HTTPS URL. Use ngrok:

```powershell
ngrok http 8001
```

Then in Copilot Studio, add a custom MCP connector pointing to
`https://<your-ngrok-id>.ngrok-free.app/mcp`.

## Quick sanity check (no Copilot Studio needed)

```powershell
pip install mcp
python -c "import asyncio; from mcp.client.streamable_http import streamablehttp_client; from mcp import ClientSession; \
async def main():
    async with streamablehttp_client('http://localhost:8001/mcp') as (r,w,_):
        async with ClientSession(r,w) as s:
            await s.initialize()
            print([t.name for t in (await s.list_tools()).tools])
asyncio.run(main())"
```
