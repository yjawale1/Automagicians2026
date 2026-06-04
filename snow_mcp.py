import os
from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Request
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

SNOW_INSTANCE = os.getenv("SNOW_INSTANCE")
SNOW_USER = os.getenv("SNOW_USER")
SNOW_PASS = os.getenv("SNOW_PASS")
DEFAULT_TABLE = os.getenv("SNOW_TABLE", "sc_request")

if not (SNOW_INSTANCE and SNOW_USER and SNOW_PASS):
    raise RuntimeError("Set SNOW_INSTANCE, SNOW_USER, SNOW_PASS in .env")

app = FastAPI(title="snow-mcp", description="ServiceNow MCP")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class SnowRequest(BaseModel):
    user_name: str
    user_email: Optional[str] = None
    justification: str
    access_items: List[str]
    project: Optional[str] = None

def create_snow_record(table: str, payload: dict):
    url = f"{SNOW_INSTANCE.rstrip('/')}/api/now/table/{table}"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers, auth=HTTPBasicAuth(SNOW_USER, SNOW_PASS), timeout=15)
    try:
        data = resp.json()
    except ValueError:
        resp.raise_for_status()
    if not resp.ok:
        raise Exception(f"SNOW API error {resp.status_code}: {data}")
    return data.get("result", {})

# JSON-RPC 2.0 Handler
def handle_jsonrpc(body: Dict[str, Any]) -> Dict[str, Any]:
    jsonrpc = body.get("jsonrpc", "2.0")
    method = body.get("method")
    params = body.get("params", {})
    req_id = body.get("id")

    logger.info(f"JSON-RPC method: {method}")

    # Notifications (no id) - just log and return None (no response)
    if req_id is None and method and method.startswith("notifications/"):
        logger.info(f"Notification received: {method}")
        return {}  # Don't send response for notifications

    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False}
                },
                "serverInfo": {
                    "name": "snow-mcp",
                    "version": "1.0.0"
                }
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "snow_request",
                        "description": "Create ServiceNow access requests for users",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "user_name": {"type": "string", "description": "Full name of the user"},
                                "user_email": {"type": "string", "description": "Email address"},
                                "justification": {"type": "string", "description": "Reason for access"},
                                "access_items": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "List of access items needed"
                                },
                                "project": {"type": "string", "description": "Project name"}
                            },
                            "required": ["user_name", "justification", "access_items"]
                        }
                    }
                ]
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_input = params.get("arguments", {})
            
            if tool_name == "snow_request":
                req = SnowRequest(**tool_input)
                results = []
                table = DEFAULT_TABLE
                for item in req.access_items:
                    short_description = f"Access request: {item} for {req.user_name}"
                    description = f"Project: {req.project or 'N/A'}\nRequester: {req.user_name} ({req.user_email or 'no-email'})\nItem: {item}\nJustification: {req.justification}"
                    payload = {"short_description": short_description, "description": description}
                    try:
                        result_record = create_snow_record(table, payload)
                    except Exception as e:
                        if table != "incident":
                            try:
                                result_record = create_snow_record("incident", payload)
                                table = "incident"
                            except Exception:
                                raise
                        else:
                            raise
                    ref = result_record.get("number") or result_record.get("sys_id")
                    results.append({"item": item, "ref": ref})
                
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Created {len(results)} ServiceNow requests: {', '.join([r['ref'] for r in results])}"
                        }
                    ]
                }
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
        else:
            raise ValueError(f"Unknown method: {method}")

        response = {"jsonrpc": jsonrpc, "result": result}
        if req_id is not None:
            response["id"] = req_id
        return response

    except Exception as e:
        logger.error(f"Error handling {method}: {str(e)}")
        error_response = {
            "jsonrpc": jsonrpc,
            "error": {
                "code": -32603,
                "message": str(e)
            }
        }
        if req_id is not None:
            error_response["id"] = req_id
        return error_response

@app.post("/")
async def root_post(request: Request):
    """JSON-RPC 2.0 endpoint for Copilot Studio"""
    body = await request.json()
    logger.info(f"Incoming: {body}")
    response = handle_jsonrpc(body)
    logger.info(f"Outgoing: {response}")
    return response if response else {"status": "ok"}  # Return empty for notifications

@app.get("/health")
def health():
    return {"status": "ok"}