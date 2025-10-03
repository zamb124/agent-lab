"""
Единый загрузчик шаблонов для всех модулей фронтенда.

Автоматически подключает все директории с шаблонами:
- shared/templates - общие шаблоны и компоненты
- modules/*/templates - шаблоны каждого модуля
"""

from pathlib import Path
from typing import List
from fastapi.templating import Jinja2Templates


class TemplateLoader:
    """Единый загрузчик шаблонов для всего фронтенда"""
    
    _instance = None
    _templates = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._templates is None:
            self._templates = self._create_templates()
    
    def _create_templates(self) -> Jinja2Templates:
        """Создать Jinja2Templates со всеми директориями"""
        frontend_dir = Path(__file__).parent.parent
        
        template_dirs = self._discover_template_dirs(frontend_dir)
        
        return Jinja2Templates(directory=[str(d) for d in template_dirs])
    
    def _discover_template_dirs(self, frontend_dir: Path) -> List[Path]:
        """Автоматически находит все директории с шаблонами"""
        dirs = []
        
        # Shared templates (первые в приоритете)
        shared_templates = frontend_dir / "shared" / "templates"
        if shared_templates.exists():
            dirs.append(shared_templates)
        
        # Модули (по алфавиту для предсказуемости)
        modules_dir = frontend_dir / "modules"
        if modules_dir.exists():
            for module_dir in sorted(modules_dir.iterdir()):
                if module_dir.is_dir():
                    module_templates = module_dir / "templates"
                    if module_templates.exists():
                        dirs.append(module_templates)
        
        # Старые templates для обратной совместимости (последние в приоритете)
        old_templates = frontend_dir / "templates"
        if old_templates.exists():
            dirs.append(old_templates)
        
        # Chat templates (для обратной совместимости)
        chat_templates = frontend_dir / "chat" / "templates"
        if chat_templates.exists():
            dirs.append(chat_templates)
        
        return dirs
    
    @property
    def templates(self) -> Jinja2Templates:
        """Получить Jinja2Templates"""
        return self._templates
    
    def reload(self):
        """Перезагрузить шаблоны (для разработки)"""
        self._templates = self._create_templates()


def get_templates() -> Jinja2Templates:
    """
    Получить единый Jinja2Templates для всех роутеров.
    
    Usage:
        from app.frontend.core.template_loader import get_templates
        
        templates = get_templates()
        return templates.TemplateResponse("page.html", {"request": request})
    """
    loader = TemplateLoader()
    return loader.templates

