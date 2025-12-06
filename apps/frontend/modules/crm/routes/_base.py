"""
Базовые утилиты для CRM роутов
"""

import logging
from typing import Optional

from fastapi import Request

from apps.frontend.core.template_loader import get_templates
from core.http import get_httpx_client

logger = logging.getLogger(__name__)
templates = get_templates()


async def fetch_crm_data(
    endpoint: str, 
    request: Request, 
    method: str = "GET", 
    json_data: dict = None
) -> dict | list:
    """Fetch data from CRM backend"""
    import os
    
    base_url = os.environ.get("TEST_CRM_SERVICE_URL")
    if not base_url:
        settings = request.app.state.settings
        base_url = getattr(settings.server, "crm_service_url", "http://localhost:8003")
    
    url = f"{base_url}/crm/api/v1{endpoint}"
    
    context = getattr(request.state, "context", None)
    auth_token = request.cookies.get("auth_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    
    company_id = ""
    if context and context.active_company:
        company_id = context.active_company.company_id
    if not company_id:
        company_id = request.headers.get("X-Company-Id", "")
    
    headers = {}
    if company_id:
        headers["X-Company-Id"] = company_id
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    
    logger.debug(f"CRM request: {url}, headers: {list(headers.keys())}, token: {'yes' if auth_token else 'no'}, company: {company_id}")
    
    try:
        async with get_httpx_client(timeout=180.0, use_proxy_from_config=False) as client:
            if method == "POST":
                response = await client.post(url, headers=headers, json=json_data or {})
            elif method == "PUT":
                response = await client.put(url, headers=headers, json=json_data or {})
            elif method == "DELETE":
                response = await client.delete(url, headers=headers)
            else:
                response = await client.get(url, headers=headers)
            
            if response.status_code == 404:
                return None
            
            if response.status_code >= 400:
                logger.error(f"CRM request failed: {method} {url} -> {response.status_code}: {response.text[:200]}")
                return None
            
            return response.json()
    except Exception as e:
        logger.error(f"CRM request error: {method} {url} -> {e}")
        return None

