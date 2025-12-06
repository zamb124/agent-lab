#!/usr/bin/env python3
"""Скрипт запуска CRM Service для разработки и debug."""

import uvicorn
from pathlib import Path

from core.config.loader import load_merged_config
from core.config import BaseSettings


if __name__ == "__main__":
    project_root = Path(__file__).parent
    service_config_path = project_root / "apps" / "crm" / "conf.json"
    
    merged_config = load_merged_config(
        base_config_path=project_root / "conf.json",
        service_config_path=service_config_path
    )
    
    settings = BaseSettings(**merged_config)
    
    print(f"Запуск CRM Service: http://{settings.server.host}:{settings.server.port}")
    
    uvicorn.run(
        "apps.crm.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=True,
        log_level="debug",
    )

