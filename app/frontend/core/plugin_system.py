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
    
    def get_header_actions(self) -> List[Dict[str, Any]]:
        """Собрать все действия для header"""
        actions = []
        for plugin in self.get_enabled():
            actions.extend(plugin.header_actions)
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

