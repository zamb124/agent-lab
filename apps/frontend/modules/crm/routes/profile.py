"""
CRM Profile - профиль пользователя
"""

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ._base import templates, fetch_crm_data

logger = logging.getLogger(__name__)
router = APIRouter(tags=["crm-profile"])


@router.get("/partials/profile", response_class=HTMLResponse)
async def partial_profile(request: Request):
    """Profile partial"""
    profile = await fetch_crm_data("/profile", request)
    stats = await fetch_crm_data("/profile/stats?days=365", request)
    
    today = date.today()
    dates = [(today - timedelta(days=370-i)).isoformat() for i in range(371)]
    
    return templates.TemplateResponse(
        "crm/partials/_profile.html",
        {
            "request": request,
            "profile": profile if isinstance(profile, dict) else {},
            "stats": stats if isinstance(stats, dict) else {},
            "dates": dates
        }
    )


@router.get("/partials/profile-modal", response_class=HTMLResponse)
async def partial_profile_modal(request: Request):
    """Edit profile modal"""
    profile = await fetch_crm_data("/profile", request)
    return templates.TemplateResponse(
        "crm/partials/_profile_modal.html",
        {
            "request": request,
            "profile": profile if isinstance(profile, dict) else {}
        }
    )


@router.put("/api/profile", response_class=HTMLResponse)
async def update_profile(request: Request):
    """Update profile via JSON"""
    body = await request.json()
    data = {
        "display_name": body.get("display_name") or None,
        "position": body.get("position") or None,
        "avatar_url": body.get("avatar_url") or None,
        "phone": body.get("phone") or None,
        "bio": body.get("bio") or None,
    }
    await fetch_crm_data("/profile", request, method="PUT", json_data=data)
    return await partial_profile(request)


@router.post("/api/profile/telegram", response_class=HTMLResponse)
async def link_telegram(request: Request):
    """Link Telegram account via JSON"""
    body = await request.json()
    telegram_id = body.get("telegram_id")
    
    if not telegram_id:
        return HTMLResponse(
            '<div class="crm-alert crm-alert-error">Telegram ID required</div>',
            status_code=400
        )
    
    data = {"telegram_username": telegram_id}
    await fetch_crm_data("/profile/telegram/link", request, method="POST", json_data=data)
    return await partial_profile(request)


@router.delete("/api/profile/telegram", response_class=HTMLResponse)
async def unlink_telegram(request: Request):
    """Unlink Telegram account"""
    await fetch_crm_data("/profile/telegram/link", request, method="DELETE")
    return await partial_profile(request)

