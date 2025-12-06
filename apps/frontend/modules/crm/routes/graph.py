"""
CRM Graph - граф знаний и поиск
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse

from ._base import templates, fetch_crm_data

logger = logging.getLogger(__name__)
router = APIRouter(tags=["crm-graph"])


@router.get("/api/v1/graph")
async def api_graph(
    request: Request,
    entity_types: Optional[str] = Query(None),
    limit: int = Query(500),
):
    """Proxy для CRM Graph API"""
    endpoint = f"/graph?limit={limit}"
    if entity_types:
        endpoint += f"&entity_types={entity_types}"
    
    data = await fetch_crm_data(endpoint, request)
    return JSONResponse(content=data or {"nodes": [], "edges": [], "stats": {"total_nodes": 0, "total_edges": 0}})


@router.get("/partials/graph", response_class=HTMLResponse)
async def partial_graph(request: Request):
    """Knowledge Graph partial"""
    graph = await fetch_crm_data("/graph", request)
    relationship_types = await fetch_crm_data("/graph/relationship-types", request)
    return templates.TemplateResponse(
        "crm/partials/_graph.html",
        {
            "request": request,
            "graph": graph,
            "relationship_types": relationship_types if isinstance(relationship_types, list) else []
        }
    )


@router.get("/partials/search", response_class=HTMLResponse)
async def partial_search(request: Request, q: str = Query("")):
    """Search results partial"""
    if not q or len(q) < 2:
        return HTMLResponse("")
    
    search_result = await fetch_crm_data("/entities/search", request, method="POST", json_data={"query": q})
    results = search_result.get("results", []) if isinstance(search_result, dict) else []
    return templates.TemplateResponse(
        "crm/partials/_search_results.html",
        {
            "request": request,
            "query": q,
            "results": results
        }
    )


@router.get("/partials/ai-suggestions-modal", response_class=HTMLResponse)
async def partial_ai_suggestions_modal(request: Request, data: str = Query("")):
    """AI suggestions modal after note analysis"""
    analysis = json.loads(data) if data else {}
    return templates.TemplateResponse(
        "crm/partials/_ai_suggestions.html",
        {"request": request, "analysis": analysis}
    )


@router.get("/partials/ai-suggestions", response_class=HTMLResponse)
async def partial_ai_suggestions(request: Request, data: str = Query("")):
    """AI suggestions modal after note analysis"""
    analysis = json.loads(data) if data else {}
    return templates.TemplateResponse(
        "crm/partials/_ai_suggestions.html",
        {"request": request, "analysis": analysis}
    )

