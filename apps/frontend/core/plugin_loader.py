"""
Автоматическая загрузка плагинов из директории modules/
"""

import importlib
import pkgutil
from pathlib import Path
from fastapi import FastAPI
from apps.frontend.core.plugin_system import get_plugin_registry, Plugin


async def discover_and_load_plugins(app: FastAPI):
    """Автоматически находит и загружает все плагины из modules/ с проверкой зависимостей"""
    
    registry = get_plugin_registry()
    modules_path = Path(__file__).parent.parent / "modules"
    
    if not modules_path.exists():
        print("⚠️ Директория modules/ не найдена")
        return
    
    print("🔍 Поиск плагинов в modules/...")
    
    plugin_instances = {}
    
    for module_info in pkgutil.iter_modules([str(modules_path)]):
        module_name = module_info.name
        
        if module_name.startswith('_'):
            continue
        
        try:
            plugin_module = importlib.import_module(
                f"apps.frontend.modules.{module_name}.plugin"
            )
            
            for attr_name in dir(plugin_module):
                attr = getattr(plugin_module, attr_name)
                
                if (isinstance(attr, type) and 
                    issubclass(attr, Plugin) and 
                    attr is not Plugin):
                    
                    plugin_instance = attr()
                    plugin_instances[plugin_instance.name] = plugin_instance
                    break
                    
        except ImportError:
            pass
        except Exception as e:
            print(f"  ❌ Ошибка загрузки {module_name}: {e}")
    
    def validate_dependencies(plugin_name: str, plugin: Plugin, visited: set, loading: set) -> bool:
        """Валидация зависимостей плагина"""
        if plugin_name in loading:
            print(f"  ❌ Циклическая зависимость обнаружена: {' -> '.join(loading)} -> {plugin_name}")
            return False
        
        if plugin_name in visited:
            return True
        
        loading.add(plugin_name)
        
        for dep_name in plugin.dependencies:
            if dep_name not in plugin_instances:
                print(f"  ❌ Плагин {plugin_name} требует {dep_name}, но он не найден")
                loading.remove(plugin_name)
                return False
            
            if not validate_dependencies(dep_name, plugin_instances[dep_name], visited, loading):
                loading.remove(plugin_name)
                return False
        
        loading.remove(plugin_name)
        visited.add(plugin_name)
        return True
    
    def topological_sort(plugins: dict) -> list:
        """Топологическая сортировка плагинов по зависимостям"""
        visited = set()
        result = []
        
        def visit(plugin_name: str):
            if plugin_name in visited:
                return
            
            plugin = plugins[plugin_name]
            
            for dep_name in plugin.dependencies:
                if dep_name in plugins:
                    visit(dep_name)
            
            visited.add(plugin_name)
            result.append(plugin_name)
        
        for plugin_name in sorted(plugins.keys()):
            if plugin_name not in visited:
                visited_deps = set()
                loading = set()
                if not validate_dependencies(plugin_name, plugins[plugin_name], visited_deps, loading):
                    print(f"  ⏭️  Пропущен плагин {plugin_name} из-за ошибок зависимостей")
                    continue
                visit(plugin_name)
        
        return result
    
    load_order = topological_sort(plugin_instances)
    loaded_count = 0
    
    for plugin_name in load_order:
        plugin_instance = plugin_instances[plugin_name]
        
        try:
            registry.register(plugin_instance)
            
            router = plugin_instance.get_router()
            if router:
                app.include_router(router)
            
            await plugin_instance.on_load(app)
            
            loaded_count += 1
        except Exception as e:
            print(f"  ❌ Ошибка регистрации плагина {plugin_name}: {e}")
    
    print(f"✅ Загружено плагинов: {loaded_count}")


def get_plugins_for_template(request=None) -> dict:
    """Получить данные плагинов для передачи в шаблоны"""
    from core.context import get_context
    
    registry = get_plugin_registry()
    
    context = get_context()
    user_role = None
    company_subdomain = None
    current_url = None
    
    if context and context.user:
        if hasattr(context.user, 'roles') and context.user.roles:
            user_role = context.user.roles[0] if context.user.roles else None
    
    if context and context.active_company:
        company_subdomain = context.active_company.subdomain
    
    if request:
        current_url = str(request.url.path)
    
    return {
        "sidebar_items": registry.get_sidebar_items(user_role, company_subdomain),
        "footer_items": registry.get_footer_items(user_role, company_subdomain),
        "dashboard_widgets": registry.get_dashboard_widgets(user_role, company_subdomain),
        "header_actions": registry.get_header_actions(user_role, company_subdomain, current_url),
        "static_files": registry.get_static_files(),
        "plugin_metadata": registry.get_plugin_metadata()
    }

