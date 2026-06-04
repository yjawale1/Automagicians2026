import os
from typing import List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Request
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()

SNOW_INSTANCE = os.getenv("SNOW_INSTANCE")
SNOW_USER = os.getenv("SNOW_USER")
SNOW_PASS = os.getenv("SNOW_PASS")
DEFAULT_TABLE = os.getenv("SNOW_TABLE", "sc_request")

if not (SNOW_INSTANCE and SNOW_USER and SNOW_PASS):
    raise RuntimeError("Set SNOW_INSTANCE, SNOW_USER, SNOW_PASS in .env")

app = FastAPI(title="snow-mcp", description="ServiceNow Access Request MCP")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Enhanced logging middleware to capture request body
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"➜ {request.method} {request.url.path}")
    body = await request.body()
    if body:
        logger.info(f"   Body: {body.decode()}")
    response = await call_next(request)
    logger.info(f"← {response.status_code}")
    return response

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

@app.get("/")
def root():
    return {"name": "snow-mcp", "version": "1.0", "description": "ServiceNow MCP for access requests"}

@app.get("/health")
def health():
    return {"status": "ok", "snow_instance": SNOW_INSTANCE}

@app.post("/")
def root_post():
    """Return OpenAPI/operation schema for Copilot Studio discovery"""
    return {
        "swagger": "2.0",
        "info": {"title": "ServiceNow MCP", "version": "1.0"},
        "paths": {
            "/snow-request": {
                "post": {
                    "operationId": "createAccessRequest",
                    "summary": "Create ServiceNow Access Request",
                    "parameters": [
                        {
                            "name": "body",
                            "in": "body",
                            "required": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "user_name": {"type": "string"},
                                    "user_email": {"type": "string"},
                                    "justification": {"type": "string"},
                                    "access_items": {"type": "array", "items": {"type": "string"}},
                                    "project": {"type": "string"}
                                },
                                "required": ["user_name", "justification", "access_items"]
                            }
                        }
                    ],
                    "responses": {
                        "200": {"description": "Requests created successfully"}
                    }
                }
            }
        }
    }

# Support both POST and GET for discovery
@app.get("/snow-request")
def snow_request_get():
    return {
        "endpoint": "/snow-request",
        "method": "POST",
        "schema": {
            "user_name": "string (required)",
            "user_email": "string (optional)",
            "justification": "string (required)",
            "access_items": "array of strings (required)",
            "project": "string (optional)"
        }
    }

@app.post("/snow-request")
def snow_request(req: SnowRequest):
    results = []
    table = DEFAULT_TABLE
    for item in req.access_items:
        short_description = f"Access request: {item} for {req.user_name}"
        description = f"Project: {req.project or 'N/A'}\nRequester: {req.user_name} ({req.user_email or 'no-email'})\nItem: {item}\nJustification: {req.justification}"
        payload = {"short_description": short_description, "description": description}
        try:
            result = create_snow_record(table, payload)
        except Exception as e:
            if table != "incident":
                try:
                    result = create_snow_record("incident", payload)
                    table = "incident"
                except Exception:
                    raise HTTPException(status_code=502, detail=str(e))
            else:
                raise HTTPException(status_code=502, detail=str(e))
        ref = result.get("number") or result.get("sys_id") or result
        results.append({"item": item, "table": table, "ref": ref, "result": result})
    return {"created": results}