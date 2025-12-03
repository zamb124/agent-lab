"""
Единый загрузчик шаблонов для всех модулей фронтенда.

Автоматически подключает все директории с шаблонами:
- shared/templates - общие шаблоны и компоненты
- modules/*/templates - шаблоны каждого модуля
"""

from datetime import date
from pathlib import Path
from typing import List

from fastapi.templating import Jinja2Templates

from core.context import get_context
from core.i18n import get_translation_manager

# Версия статики - дата запуска приложения (обновляется при рестарте)
STATIC_VERSION = date.today().strftime("%Y%m%d")


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
        
        def user_companies():
            """Получить все компании пользователя"""
            context = get_context()
            
            # Сначала пробуем получить из контекста
            if context and hasattr(context, 'user_companies') and isinstance(context.user_companies, list):
                return context.user_companies
            
            # Если контекст очищен (например в middleware), пытаемся получить из request.state
            try:
                # Получаем request из контекста шаблона (передается автоматически)
                if 'request' in globals() or hasattr(self, '_request'):
                    request = globals().get('request') or getattr(self, '_request', None)
                    if request and hasattr(request, 'state') and hasattr(request.state, 'user_companies'):
                        return request.state.user_companies or []
            except Exception:
                pass
            
            return []
        
        def t(key: str, **kwargs) -> str:
            """Функция перевода для шаблонов"""
            try:
                manager = get_translation_manager()
                return manager.t(key, **kwargs)
            except Exception:
                # Если что-то пошло не так, возвращаем ключ
                return key
        
        def t_field(field_info: dict, attr: str = "title") -> str:
            """Перевод атрибутов поля с поддержкой i18n ключей"""
            try:
                # Проверяем что field_info валидный
                if not field_info or not isinstance(field_info, dict):
                    return ""
                
                # Сначала пытаемся использовать i18n ключ
                i18n_key = field_info.get(f"i18n_{attr}")
                if i18n_key:
                    manager = get_translation_manager()
                    translation = manager.t(i18n_key)
                    # Если перевод найден (не равен ключу), используем его
                    if translation != i18n_key:
                        return translation
                
                # Иначе возвращаем оригинальное значение
                return field_info.get(attr, "")
            except Exception:
                # При ошибке возвращаем пустую строку или оригинальное значение
                if field_info and isinstance(field_info, dict):
                    return field_info.get(attr, "")
                return ""
        
        def get_current_language() -> str:
            """Получить текущий язык пользователя"""
            try:
                context = get_context()
                if context and hasattr(context, 'language'):
                    return context.language.value
                return 'ru'
            except Exception:
                return 'ru'
        
        def static(path: str) -> str:
            """Путь к статическому файлу с версией для сброса кэша браузера"""
            if path.startswith("/"):
                return f"/static{path}?v={STATIC_VERSION}"
            return f"/static/{path}?v={STATIC_VERSION}"

        templates.env.globals['current_user'] = get_current_user
        templates.env.globals['current_company'] = get_current_company
        templates.env.globals['user_roles'] = user_roles
        templates.env.globals['user_has_role'] = user_has_role
        templates.env.globals['is_system_admin'] = is_system_admin
        templates.env.globals['user_companies'] = user_companies
        # Функции интернационализации
        templates.env.globals['t'] = t
        templates.env.globals['t_field'] = t_field
        templates.env.globals['get_current_language'] = get_current_language
        templates.env.globals['static'] = static
        
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
        
        # Pages (публичные страницы)
        pages_dir = frontend_dir / "pages"
        if pages_dir.exists():
            for page_dir in sorted(pages_dir.iterdir()):
                if page_dir.is_dir():
                    page_templates = page_dir / "templates"
                    if page_templates.exists():
                        dirs.append(page_templates)
        
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
        from apps.frontend.core.template_loader import get_templates
        
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

