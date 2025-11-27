"""
Роутер модуля Store - магазин готовых flows
"""

import logging
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from apps.frontend.core.template_loader import get_templates
from apps.frontend.core.utils import render_with_dashboard
from apps.frontend.dependencies import FlowRepositoryDep

router = APIRouter(prefix="/frontend/store", tags=["store-pages"])
templates = get_templates()
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def store_page(request: Request):
    """Главная страница Store"""
    return await render_with_dashboard(
        request=request,
        content_template="store.html",
        context={"request": request},
        content_url="/frontend/store/",
    )


@router.get("/list", response_class=HTMLResponse)
async def store_list(request: Request, flow_repo: FlowRepositoryDep):
    """Список публичных flows из кода (оптимизировано)"""
    agents_container = request.app.state.agents_container
    if not agents_container:
        return templates.TemplateResponse("components/store/store_list.html", {
            "request": request,
            "flows": [],
            "error": "AgentsContainer не инициализирован"
        })
    migrator = agents_container.migrator
    
    flows_with_ids = await migrator.get_public_flows()
    
    all_flows = await flow_repo.list_all(limit=1000)
    installed_flow_ids = {flow.flow_id for flow in all_flows}
    
    flows = []
    for full_flow_id, flow_config in flows_with_ids:
        flow_id_for_check = flow_config.flow_id or flow_config.name.lower().replace(' ', '_')
        
        installed = full_flow_id in installed_flow_ids or flow_id_for_check in installed_flow_ids
        
        author_dict = None
        if hasattr(flow_config, 'author') and flow_config.author:
            author_dict = flow_config.author.model_dump() if hasattr(flow_config.author, 'model_dump') else flow_config.author
        
        image_url = '/static/img/empty.png'
        if hasattr(flow_config, 'image_path') and flow_config.image_path:
            image_url = f"/frontend/store/flow-image/{full_flow_id}"
        elif hasattr(flow_config, 'image_file_id') and flow_config.image_file_id:
            image_url = f"/agents/api/v1/files/{flow_config.image_file_id}"
        
        flow_info = {
            "flow_id": full_flow_id,
            "name": flow_config.name,
            "description": flow_config.description or 'Описание отсутствует',
            "platforms": list(flow_config.platforms.keys()) if flow_config.platforms else [],
            "image_url": image_url,
            "author": author_dict,
            "installed": installed,
        }
        flows.append(flow_info)
    
    return templates.TemplateResponse(
        "store_list.html",
        {"request": request, "flows": flows}
    )


@router.get("/{flow_id:path}/details", response_class=HTMLResponse)
async def flow_details(request: Request, flow_id: str):
    """Детальная информация о flow из кода (для модалки)"""
    logger.info(f"Flow details requested for: {flow_id}")

    agents_container = request.app.state.agents_container
    if not agents_container:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "AgentsContainer не инициализирован"}
        )
    
    migrator = agents_container.migrator
    flows_with_ids = await migrator.get_public_flows()
    logger.info(f"Found {len(flows_with_ids)} public flows")

    flow_config = None
    for full_flow_id, flow in flows_with_ids:
        logger.info(f"Checking flow: {full_flow_id}")
        if full_flow_id == flow_id:
            flow_config = flow
            logger.info(f"Found matching flow: {full_flow_id}")
            break
    
    if not flow_config:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Flow не найден"}
        )
    
    flow_repo = agents_container.flow_repository
    installed = await flow_repo.get(flow_id) is not None
    
    author_dict = None
    if hasattr(flow_config, 'author') and flow_config.author:
        author_dict = flow_config.author.model_dump() if hasattr(flow_config.author, 'model_dump') else flow_config.author
    
    image_url = '/static/img/empty.png'
    if hasattr(flow_config, 'image_path') and flow_config.image_path:
        image_url = f"/frontend/store/flow-image/{flow_id}"
    elif hasattr(flow_config, 'image_file_id') and flow_config.image_file_id:
        image_url = f"/agents/api/v1/files/{flow_config.image_file_id}"
    
    flow_info = {
        "flow_id": flow_id,
        "name": flow_config.name,
        "description": flow_config.description or "Описание отсутствует",
        "platforms": flow_config.platforms or {},
        "image_url": image_url,
        "author": author_dict,
        "installed": installed,
        "variables_definitions": getattr(flow_config, 'variables_definitions', []),
    }
    
    return templates.TemplateResponse(
        "flow_details_modal.html",
        {"request": request, "flow": flow_info}
    )


@router.get("/flow-image/{flow_id:path}")
async def get_flow_image(request: Request, flow_id: str):
    """Отдает картинку flow из проекта"""
    agents_container = request.app.state.agents_container
    if not agents_container:
        raise HTTPException(status_code=500, detail="AgentsContainer не инициализирован")
    
    migrator = agents_container.migrator
    flows_with_ids = await migrator.get_public_flows()
    
    flow_config = None
    for full_flow_id, flow in flows_with_ids:
        if full_flow_id == flow_id:
            flow_config = flow
            break
    
    if not flow_config:
        raise HTTPException(status_code=404, detail="Flow не найден")
    
    if not hasattr(flow_config, 'image_path') or not flow_config.image_path:
        raise HTTPException(status_code=404, detail="У flow нет картинки")
    
    image_path = Path(flow_config.image_path)
    
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Файл картинки не найден")
    
    return FileResponse(
        path=str(image_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"}
    )

