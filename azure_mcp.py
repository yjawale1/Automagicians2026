# azure_mcp.py
import logging
from typing import Any, Dict
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("azure-mcp")

app = FastAPI(title="azure-mcp")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Mock Azure data
MOCK_REPOS = {
    "cibc-payments-api": {
        "id": "repo-001",
        "name": "cibc-payments-api",
        "url": "https://dev.azure.com/cibc/Payments/_git/cibc-payments-api",
        "access_requirements": ["Contributor", "Build Admin"],
        "team": "Payments Platform",
    },
    "cibc-payments-frontend": {
        "id": "repo-002",
        "name": "cibc-payments-frontend",
        "url": "https://dev.azure.com/cibc/Payments/_git/cibc-payments-frontend",
        "access_requirements": ["Reader", "Contributor"],
        "team": "Payments Platform",
    },
    "cibc-shared-libs": {
        "id": "repo-003",
        "name": "cibc-shared-libs",
        "url": "https://dev.azure.com/cibc/Platform/_git/cibc-shared-libs",
        "access_requirements": ["Reader"],
        "team": "Platform",
    },
}

MOCK_PROJECTS = {
    "Payments": {"name": "Payments", "team": "Payments Platform", "repos": ["cibc-payments-api", "cibc-payments-frontend"]},
    "Platform": {"name": "Platform", "team": "Platform", "repos": ["cibc-shared-libs"]},
}

MOCK_ACCESS_MATRIX = {
    "APP-12345": {  # Payments Platform MapID
        "project": "Payments",
        "repos": ["cibc-payments-api", "cibc-payments-frontend", "cibc-shared-libs"],
        "keyvaults": ["payments-dev-kv", "payments-prod-kv"],
        "pipelines": ["payments-api-ci", "payments-ui-cd"],
        "approvers": ["alice@cibc.com", "bob@cibc.com"],
    }
}


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
                "serverInfo": {"name": "azure-mcp", "version": "1.0.0"},
            }
            return mk_response(req_id, res)

        if method == "tools/list":
            tools = [
                {
                    "name": "list_azure_repos",
                    "description": "List all Azure DevOps repositories",
                    "inputSchema": {"type": "object"},
                },
                {
                    "name": "get_repo_access_requirements",
                    "description": "Get access requirements for a specific repo",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"repo_name": {"type": "string"}},
                        "required": ["repo_name"],
                    },
                },
                {
                    "name": "get_project_requirements",
                    "description": "Get all Azure access required for a project MapID",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"map_id": {"type": "string"}},
                        "required": ["map_id"],
                    },
                },
            ]
            return mk_response(req_id, {"tools": tools})

        if method == "tools/call":
            params = body.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}

            if name == "list_azure_repos":
                result = [
                    {
                        "name": repo,
                        "url": data["url"],
                        "team": data["team"],
                        "access_requirements": data["access_requirements"],
                    }
                    for repo, data in MOCK_REPOS.items()
                ]
            elif name == "get_repo_access_requirements":
                repo_name = arguments.get("repo_name")
                if repo_name in MOCK_REPOS:
                    result = {
                        "repo": repo_name,
                        "url": MOCK_REPOS[repo_name]["url"],
                        "access_requirements": MOCK_REPOS[repo_name]["access_requirements"],
                        "team": MOCK_REPOS[repo_name]["team"],
                    }
                else:
                    raise ValueError(f"Repo not found: {repo_name}")
            elif name == "get_project_requirements":
                map_id = arguments.get("map_id")
                if map_id in MOCK_ACCESS_MATRIX:
                    access = MOCK_ACCESS_MATRIX[map_id]
                    result = {
                        "map_id": map_id,
                        "project": access["project"],
                        "repos": access["repos"],
                        "keyvaults": access["keyvaults"],
                        "pipelines": access["pipelines"],
                        "approvers": access["approvers"],
                        "summary": f"For {access['project']} project: need access to {len(access['repos'])} repos, {len(access['keyvaults'])} key vaults, and {len(access['pipelines'])} pipelines",
                    }
                else:
                    raise ValueError(f"MapID not found: {map_id}")
            else:
                raise ValueError(f"Unknown tool: {name}")

            return mk_response(req_id, {"content": [{"type": "json", "value": result}]})

        if req_id is None:
            return {}
        return mk_response(req_id, None, {"code": -32601, "message": "Unknown method"})
    except Exception as e:
        log.exception("RPC error")
        return mk_response(req_id, None, {"code": -32603, "message": str(e)})


@app.get("/health")
async def health():
    return {"status": "ok"}