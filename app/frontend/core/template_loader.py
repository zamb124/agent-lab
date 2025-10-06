"""
Единый загрузчик шаблонов для всех модулей фронтенда.

Автоматически подключает все директории с шаблонами:
- shared/templates - общие шаблоны и компоненты
- modules/*/templates - шаблоны каждого модуля
"""

from pathlib import Path
from typing import List, Dict, Any
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.responses import Response
from app.core.context import get_context


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
        
        templates = Jinja2Templates(directory=[str(d) for d in template_dirs])
        
        # Добавляем глобальные переменные для доступа к контексту
        def get_current_user():
            context = get_context()
            return context.user if context else None
        
        def get_current_company():
            context = get_context()
            return context.active_company if context else None
        
        def user_roles():
            """Получить роли пользователя в активной компании"""
            context = get_context()
            if not context or not context.user or not context.active_company:
                return ["user"]
            
            company_id = context.active_company.company_id
            if company_id in context.user.companies:
                return context.user.companies[company_id]
            
            return ["user"]
        
        def user_has_role(role_name: str, company_id: str = None):
            """Проверить что у пользователя есть роль в компании"""
            context = get_context()
            if not context or not context.user:
                return False
            
            # Если компания не указана - используем активную
            target_company = company_id
            if not target_company and context.active_company:
                target_company = context.active_company.company_id
            
            if not target_company:
                return False
            
            # Проверяем роли в компании
            if target_company in context.user.companies:
                return role_name in context.user.companies[target_company]
            
            return False
        
        def is_system_admin():
            context = get_context()
            if not context or not context.user:
                return False
            user = context.user
            
            # Проверяем что у пользователя есть роль admin в компании system
            if "system" in user.companies:
                system_roles = user.companies["system"]
                if "admin" in system_roles:
                    return True
            
            return False
        
        templates.env.globals['current_user'] = get_current_user
        templates.env.globals['current_company'] = get_current_company
        templates.env.globals['user_roles'] = user_roles
        templates.env.globals['user_has_role'] = user_has_role
        templates.env.globals['is_system_admin'] = is_system_admin
        
        return templates
    
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


def render_template(template_name: str, **context) -> str:
    """
    Рендерить шаблон напрямую в HTML строку.
    
    Args:
        template_name: Имя шаблона
        **context: Контекст для рендеринга
        
    Returns:
        HTML строка
        
    Raises:
        FileNotFoundError: Если шаблон не найден
    """
    templates = get_templates()
    
    try:
        template = templates.env.get_template(template_name)
        return template.render(**context)
    except Exception as e:
        raise FileNotFoundError(f"Template not found: {template_name} (Error: {e})")


def template_exists(template_name: str) -> bool:
    """
    Проверить существование шаблона.
    
    Args:
        template_name: Имя шаблона
        
    Returns:
        True если шаблон существует, False иначе
    """
    templates = get_templates()
    
    try:
        templates.env.get_template(template_name)
        return True
    except Exception:
        return False

