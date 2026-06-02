import os
import json
import requests
import pandas as pd
from io import StringIO
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, PlainTextResponse

from mcp.server import Server  # Add this line right above your server initialization
from mcp.types import Tool, TextContent

server = Server("GitHub_Banking_Data_Server_v2")

# Your live raw GitHub repository URL
CSV_URL = "https://raw.githubusercontent.com/yjawale1/Automagicians2026/refs/heads/main/dummy_banking_records.csv"

def fetch_csv_data() -> pd.DataFrame:
    response = requests.get(CSV_URL)
    response.raise_for_status()
    return pd.read_csv(StringIO(response.text))

# Shared tools schema definition block
TOOLS_SCHEMA = [
    {
        "name": "query_banking_data",
        "description": "Queries dummy banking records from GitHub. Allows filtering by column and value.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter_column": {"type": "string", "description": "The name of the column to filter on"},
                "filter_value": {"type": "string", "description": "The row value matching the filter column"},
                "limit": {"type": "integer", "description": "Maximum number of records to pull"}
            }
        }
    }
]

async def handle_call_tool(arguments: dict) -> list:
    if not isinstance(arguments, dict):
        arguments = {}
        
    filter_column = arguments.get("filter_column")
    filter_value = arguments.get("filter_value")
    limit = arguments.get("limit")
    
    try:
        limit = int(limit) if limit is not None else 10
    except (ValueError, TypeError):
        limit = 10
    
    try:
        df = fetch_csv_data()
        
        if filter_column and filter_value:
            filter_column_str = str(filter_column).strip()
            filter_value_str = str(filter_value).strip()
            
            if filter_column_str in df.columns:
                df = df[df[filter_column_str].astype(str).str.contains(filter_value_str, case=False, na=False)]
            else:
                return [{"error": f"Column '{filter_column_str}' not found. Available: {list(df.columns)}"}]
        
        records = df.head(limit).fillna("").to_dict(orient="records")
        return records
    except Exception as e:
        return [{"error": f"Error reading data: {str(e)}"}]

# Complete Hybrid ASGI Routing Engine handling all phases of the MCP Lifecycle
async def copilot_native_asgi_app(scope, receive, send):
    if scope["type"] != "http":
        return

    method = scope.get("method", "GET")
    path = scope.get("path", "/")

    if method == "POST":
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            body += message.get("body", b"")
            more_body = message.get("more_body", False)

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        is_jsonrpc = isinstance(payload, dict) and "jsonrpc" in payload
        rpc_method = payload.get("method") if is_jsonrpc else None
        request_id = payload.get("id", 1)

        # 1. STEP 1: INITIALIZATION HANDSHAKE
        if rpc_method == "initialize":
            print("Processing strict MCP initialization handshake...")
            response_body = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {} # Explicitly flags tool capacity
                    },
                    "serverInfo": {"name": "GitHub_Banking_Data_Server_v2", "version": "1.0"}
                }
            }
            response = JSONResponse(response_body, status_code=200)
            await response(scope, receive, send)
            return

        # 2. STEP 2: TOOL LIST QUERY (Populates the empty UI box)
        elif rpc_method == "tools/list" or path.endswith("/tools") or (not is_jsonrpc and "filter_column" not in payload and "filter_value" not in payload):
            print("Processing tools/list request to populate UI components...")
            response_body = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": TOOLS_SCHEMA
                }
            }
            response = JSONResponse(response_body, status_code=200)
            await response(scope, receive, send)
            return

        # 3. STEP 3: TOOL EXECUTION RUNS
        else:
            print("Processing tool execution data request...")
            if is_jsonrpc and rpc_method == "tools/call":
                args = payload.get("params", {}).get("arguments", {})
            else:
                args = payload

            data_records = await handle_call_tool(args)
            
            if is_jsonrpc:
                response_body = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(data_records)}]
                    }
                }
            else:
                response_body = {
                    "records": data_records,
                    "status": "success"
                }
                
            response = JSONResponse(response_body, status_code=200)
            await response(scope, receive, send)
            return

    if method == "GET":
        response = PlainTextResponse("Server is healthy and listening for Claude agent requests.", status_code=200)
        await response(scope, receive, send)
        return

# Global CORS configurations
middleware = [
    Middleware(
        CORSMiddleware, 
        allow_origins=["*"], 
        allow_methods=["*"], 
        allow_headers=["*"]
    )
]

app = Starlette(middleware=middleware)
app.mount("/", app=copilot_native_asgi_app)

if __name__ == "__main__":
    import uvicorn
    print("Launching Full-Lifecycle Hybrid Server on http://0.0.0.0:8000 ...")
    uvicorn.run(app, host="0.0.0.0", port=8000)