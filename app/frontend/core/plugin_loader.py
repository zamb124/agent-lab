"""
Автоматическая загрузка плагинов из директории modules/
"""

import importlib
import pkgutil
from pathlib import Path
from fastapi import FastAPI
from app.frontend.core.plugin_system import get_plugin_registry, Plugin


async def discover_and_load_plugins(app: FastAPI):
    """Автоматически находит и загружает все плагины из modules/"""
    
    registry = get_plugin_registry()
    modules_path = Path(__file__).parent.parent / "modules"
    
    if not modules_path.exists():
        print("⚠️ Директория modules/ не найдена")
        return
    
    print("🔍 Поиск плагинов в modules/...")
    
    loaded_count = 0
    
    for module_info in pkgutil.iter_modules([str(modules_path)]):
        module_name = module_info.name
        
        if module_name.startswith('_'):
            continue
        
        try:
            plugin_module = importlib.import_module(
                f"app.frontend.modules.{module_name}.plugin"
            )
            
            for attr_name in dir(plugin_module):
                attr = getattr(plugin_module, attr_name)
                
                if (isinstance(attr, type) and 
                    issubclass(attr, Plugin) and 
                    attr is not Plugin):
                    
                    plugin_instance = attr()
                    
                    registry.register(plugin_instance)
                    
                    router = plugin_instance.get_router()
                    if router:
                        app.include_router(router)
                    
                    await plugin_instance.on_load(app)
                    
                    loaded_count += 1
                    break
                    
        except ImportError as e:
            print(f"  ⏭️  {module_name} - нет plugin.py (пропускаем)")
        except Exception as e:
            print(f"  ❌ Ошибка загрузки {module_name}: {e}")
    
    print(f"✅ Загружено плагинов: {loaded_count}")


def get_plugins_for_template() -> dict:
    """Получить данные плагинов для передачи в шаблоны"""
    from app.core.context import get_context
    
    registry = get_plugin_registry()
    
    context = get_context()
    user_role = None
    company_subdomain = None
    
    if context and context.user:
        if hasattr(context.user, 'roles') and context.user.roles:
            user_role = context.user.roles[0] if context.user.roles else None
    
    if context and context.active_company:
        company_subdomain = context.active_company.subdomain
    
    return {
        "sidebar_items": registry.get_sidebar_items(user_role, company_subdomain),
        "footer_items": registry.get_footer_items(user_role, company_subdomain),
        "dashboard_widgets": registry.get_dashboard_widgets(user_role, company_subdomain),
        "header_actions": registry.get_header_actions(),
        "static_files": registry.get_static_files(),
        "plugin_metadata": registry.get_plugin_metadata()
    }

