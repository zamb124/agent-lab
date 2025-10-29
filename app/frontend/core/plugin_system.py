"""
Плагинная система для фронтенда

Позволяет создавать модульные расширения с автоматической регистрацией.
"""

from typing import List, Dict, Optional, Any
from abc import ABC, abstractmethod
from fastapi import APIRouter, FastAPI


class Plugin(ABC):
    """Базовый класс для всех плагинов фронтенда"""
    
    name: str
    display_name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = "Agents Lab"
    
    dependencies: List[str] = []
    requires_auth: bool = True
    requires_role: Optional[str] = None
    requires_company: Optional[str] = None
    
    static_css: List[str] = []
    static_js: List[str] = []
    
    sidebar_items: List[Dict[str, Any]] = []
    footer_items: List[Dict[str, Any]] = []
    dashboard_widgets: List[Dict[str, Any]] = []
    header_actions: List[Dict[str, Any]] = []
    
    @abstractmethod
    def get_router(self) -> APIRouter:
        """Возвращает FastAPI роутер модуля"""
        pass
    
    async def on_load(self, app: FastAPI):
        """Хук при загрузке плагина"""
        pass
    
    async def on_enable(self):
        """Хук при включении плагина"""
        pass
    
    async def on_disable(self):
        """Хук при отключении плагина"""
        pass
    
    def get_header_actions(self, current_url: Optional[str] = None, user_role: Optional[str] = None, company_subdomain: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Получить динамические header actions с учетом контекста
        
        Переопределите этот метод для возврата динамических действий в зависимости от текущей страницы.
        
        Args:
            current_url: Текущий URL пути
            user_role: Роль пользователя
            company_subdomain: Subdomain компании
        
        Returns:
            Список действий или None для использования статических header_actions
        """
        return None
    
    async def modify_template_context(self, context: Dict[str, Any], request: Optional[Any] = None) -> Dict[str, Any]:
        """Хук для модификации контекста шаблона перед рендерингом
        
        Позволяет плагину изменить или добавить данные в контекст шаблона.
        
        Args:
            context: Словарь контекста для шаблона
            request: FastAPI Request объект
        
        Returns:
            Модифицированный контекст
        """
        return context
    
    def get_sidebar_modifications(self) -> Dict[str, Any]:
        """Получить модификации для sidebar
        
        Возвращает словарь с опциями для изменения рендеринга sidebar:
        - before_items: HTML для вставки перед элементами
        - after_items: HTML для вставки после элементов
        - custom_css: Дополнительные CSS классы
        
        Returns:
            Словарь с модификациями или пустой dict
        """
        return {}
    
    def get_header_modifications(self) -> Dict[str, Any]:
        """Получить модификации для header
        
        Возвращает словарь с опциями для изменения рендеринга header:
        - before_actions: HTML для вставки перед действиями
        - after_actions: HTML для вставки после действий
        - custom_css: Дополнительные CSS классы
        
        Returns:
            Словарь с модификациями или пустой dict
        """
        return {}
    
    def get_static_paths(self) -> Dict[str, List[str]]:
        """Получить пути к статическим файлам"""
        css_paths = [f"/static/{self.name}/css/{f}" for f in self.static_css]
        js_paths = [f"/static/{self.name}/js/{f}" for f in self.static_js]
        return {"css": css_paths, "js": js_paths}


class PluginRegistry:
    """Реестр всех плагинов"""
    
    def __init__(self):
        self.plugins: Dict[str, Plugin] = {}
        self.enabled_plugins: set = set()
        self._load_order: List[str] = []
    
    def register(self, plugin: Plugin):
        """Регистрация плагина"""
        if not hasattr(plugin, 'name') or not plugin.name:
            raise ValueError("Плагин должен иметь атрибут 'name'")
        
        if plugin.name in self.plugins:
            raise ValueError(f"Плагин {plugin.name} уже зарегистрирован")
        
        self.plugins[plugin.name] = plugin
        self.enabled_plugins.add(plugin.name)
        self._load_order.append(plugin.name)
        
        print(f"✅ Плагин {plugin.display_name or plugin.name} зарегистрирован")
    
    def get(self, name: str) -> Optional[Plugin]:
        """Получить плагин по имени"""
        return self.plugins.get(name)
    
    def get_all(self) -> List[Plugin]:
        """Все зарегистрированные плагины"""
        return [self.plugins[name] for name in self._load_order if name in self.plugins]
    
    def get_enabled(self) -> List[Plugin]:
        """Только включенные плагины"""
        return [
            self.plugins[name] 
            for name in self._load_order 
            if name in self.enabled_plugins
        ]
    
    def enable(self, name: str):
        """Включить плагин"""
        if name in self.plugins:
            self.enabled_plugins.add(name)
    
    def disable(self, name: str):
        """Отключить плагин"""
        if name in self.enabled_plugins:
            self.enabled_plugins.remove(name)
    
    def get_sidebar_items(self, user_role: Optional[str] = None, company_subdomain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Собрать все пункты sidebar из плагинов"""
        items = []
        for plugin in self.get_enabled():
            if user_role and plugin.requires_role and plugin.requires_role != user_role:
                continue
            if plugin.requires_company and plugin.requires_company != company_subdomain:
                continue
            items.extend(plugin.sidebar_items)
        
        return sorted(items, key=lambda x: x.get('order', 100))
    
    def get_footer_items(self, user_role: Optional[str] = None, company_subdomain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Собрать все пункты footer из плагинов"""
        items = []
        for plugin in self.get_enabled():
            if user_role and plugin.requires_role and plugin.requires_role != user_role:
                continue
            if plugin.requires_company and plugin.requires_company != company_subdomain:
                continue
            items.extend(plugin.footer_items)
        
        return sorted(items, key=lambda x: x.get('order', 100))
    
    def get_dashboard_widgets(self, user_role: Optional[str] = None, company_subdomain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Собрать все виджеты dashboard"""
        widgets = []
        for plugin in self.get_enabled():
            if user_role and plugin.requires_role and plugin.requires_role != user_role:
                continue
            if plugin.requires_company and plugin.requires_company != company_subdomain:
                continue
            widgets.extend(plugin.dashboard_widgets)
        return sorted(widgets, key=lambda x: x.get('order', 100))
    
    def _match_url_pattern(self, pattern: str, url: str) -> bool:
        """Проверяет соответствует ли URL паттерну
        
        Правила:
        - Точное совпадение: '/frontend/bots/' == '/frontend/bots/'
        - С вариацией слэша: '/frontend/bots/' == '/frontend/bots' и наоборот
        - Паттерны с *: '/frontend/bots/*/details' матчит '/frontend/bots/123/details'
        - Если паттерн заканчивается на /: '/frontend/bots/' матчит все URL начинающиеся с '/frontend/bots/'
        - Если паттерн без /: '/frontend/bots' матчит только '/frontend/bots' и '/frontend/bots/'
        """
        if pattern == url:
            return True
        
        if pattern.endswith('/') and url == pattern.rstrip('/'):
            return True
        
        if not pattern.endswith('/') and url == pattern + '/':
            return True
        
        if '*' in pattern:
            import re
            regex_pattern = pattern.replace('*', '[^/]+')
            regex_pattern = regex_pattern.replace('/', r'\/')
            regex_pattern = f'^{regex_pattern}$'
            return bool(re.match(regex_pattern, url))
        
        # Если паттерн заканчивается на /, то URL должен начинаться с него (для всех подпутей)
        if pattern.endswith('/'):
            return url.startswith(pattern)
        
        return False
    
    def get_header_actions(self, user_role: Optional[str] = None, company_subdomain: Optional[str] = None, current_url: Optional[str] = None) -> List[Dict[str, Any]]:
        """Собрать все действия для header с поддержкой контекста и фильтрации по URL"""
        actions = []
        
        for plugin in self.get_enabled():
            if user_role and plugin.requires_role and plugin.requires_role != user_role:
                continue
            if plugin.requires_company and plugin.requires_company != company_subdomain:
                continue
            
            for action in plugin.header_actions:
                action_urls = action.get('urls', [])
                
                if not action_urls:
                    actions.append(action)
                    continue
                
                if not current_url:
                    continue
                
                matches = any(self._match_url_pattern(pattern, current_url) for pattern in action_urls)
                if matches:
                    actions.append(action)
        
        return sorted(actions, key=lambda x: x.get('order', 100))
    
    def get_static_files(self) -> Dict[str, List[str]]:
        """Собрать все статические файлы"""
        css = []
        js = []
        for plugin in self.get_enabled():
            paths = plugin.get_static_paths()
            css.extend(paths['css'])
            js.extend(paths['js'])
        return {"css": css, "js": js}
    
    def get_plugin_metadata(self) -> List[Dict[str, Any]]:
        """Получить метаданные всех плагинов для передачи в JS"""
        metadata = []
        for plugin in self.get_enabled():
            metadata.append({
                "name": plugin.name,
                "display_name": plugin.display_name,
                "version": plugin.version,
                "has_js": bool(plugin.static_js),
                "main_js": plugin.static_js[0] if plugin.static_js else None
            })
        return metadata


_registry = PluginRegistry()


def get_plugin_registry() -> PluginRegistry:
    """Получить глобальный реестр плагинов"""
    return _registry

