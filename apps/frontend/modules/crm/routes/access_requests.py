"""
CRM Access Requests - запросы доступа
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

from ._base import templates, fetch_crm_data

logger = logging.getLogger(__name__)
router = APIRouter(tags=["crm-access-requests"])


def _parse_request_dates(requests_data: list) -> list:
    """Парсит строковые даты в datetime объекты для шаблона"""
    if not isinstance(requests_data, list):
        return []
    
    for req in requests_data:
        if isinstance(req, dict) and req.get("created_at"):
            try:
                if isinstance(req["created_at"], str):
                    req["created_at"] = datetime.fromisoformat(
                        req["created_at"].replace("Z", "+00:00")
                    )
            except (ValueError, TypeError):
                pass
    return requests_data


@router.get("/partials/access-requests", response_class=HTMLResponse)
async def partial_access_requests(
    request: Request,
    tab: str = Query("incoming", description="incoming or outgoing")
):
    """Access Requests partial"""
    if tab == "incoming":
        requests_data = await fetch_crm_data("/access-requests/incoming", request)
    else:
        requests_data = await fetch_crm_data("/access-requests/outgoing", request)
    
    # Парсим даты для корректного отображения в шаблоне
    requests_data = _parse_request_dates(requests_data)
    
    pending_count_data = await fetch_crm_data("/access-requests/pending-count", request)
    pending_count = pending_count_data.get("count", 0) if isinstance(pending_count_data, dict) else 0
    
    return templates.TemplateResponse(
        "crm/partials/_access_requests.html",
        {
            "request": request,
            "requests": requests_data,
            "tab": tab,
            "pending_count": pending_count
        }
    )


@router.get("/partials/request-access-modal", response_class=HTMLResponse)
async def partial_request_access_modal(
    request: Request,
    resource_type: str = Query(...),
    resource_id: str = Query(...)
):
    """Request access modal"""
    resource_title = None
    owner_id = None
    
    if resource_type == "note":
        try:
            note = await fetch_crm_data(f"/notes/{resource_id}", request)
            if note:
                resource_title = note.get("title")
                owner_id = note.get("user_id")
        except Exception:
            pass
    
    return templates.TemplateResponse(
        "crm/partials/_request_access_modal.html",
        {
            "request": request,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "resource_title": resource_title,
            "owner_id": owner_id,
        }
    )


# === API ===

@router.get("/api/access-requests/pending-count", response_class=HTMLResponse)
async def get_access_requests_pending_count(request: Request):
    """Get pending access requests count as badge HTML"""
    pending_data = await fetch_crm_data("/access-requests/pending-count", request)
    count = pending_data.get("count", 0) if isinstance(pending_data, dict) else 0
    
    if count > 0:
        return HTMLResponse(f'<span class="crm-badge crm-badge-danger">{count}</span>')
    return HTMLResponse("")


@router.post("/api/access-requests", response_class=HTMLResponse)
async def create_access_request(request: Request):
    """Create access request via JSON"""
    body = await request.json()
    data = {
        "resource_type": body.get("resource_type"),
        "resource_id": body.get("resource_id"),
        "message": body.get("message"),
    }
    try:
        await fetch_crm_data("/access-requests", request, method="POST", json_data=data)
        return HTMLResponse("""
            <script>
                CRM.closeModal();
                CRM.showNotification('Запрос отправлен', 'success');
            </script>
        """)
    except Exception as e:
        return HTMLResponse(f"""
            <div class="crm-alert crm-alert-error">
                <i class="ti ti-alert-circle"></i>
                {str(e)}
            </div>
        """)


@router.post("/api/access-requests/{request_id}/approve", response_class=HTMLResponse)
async def approve_access_request(request: Request, request_id: str):
    """Approve access request"""
    await fetch_crm_data(f"/access-requests/{request_id}/approve", request, method="POST")
    return await partial_access_requests(request, tab="incoming")


@router.post("/api/access-requests/{request_id}/reject", response_class=HTMLResponse)
async def reject_access_request(request: Request, request_id: str):
    """Reject access request"""
    await fetch_crm_data(f"/access-requests/{request_id}/reject", request, method="POST")
    return await partial_access_requests(request, tab="incoming")

