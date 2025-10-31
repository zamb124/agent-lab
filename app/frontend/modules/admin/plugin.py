"""
Admin Plugin - администрирование
"""

from app.frontend.core.plugin_system import Plugin


class AdminPlugin(Plugin):
    """Плагин администрирования"""
    
    name = "admin"
    display_name = "Администрирование"
    version = "1.0.0"
    description = "Управление компаниями и системой"
    author = "Agents Lab"
    
    requires_auth = True
    requires_role = None
    requires_company = "system"
    
    static_css = ["admin.css"]
    static_js = []
    
    sidebar_items = [
        {
            "id": "admin",
            "label": "Администрирование",
            "icon": "shield-lock",
            "type": "submenu",
            "order": 100,
            "group": "Система",
            "group_icon": "settings",
            "group_order": 90,
            "children": [
                {
                    "id": "admin_users",
                    "label": "Пользователи",
                    "icon": "people",
                    "url": "/frontend/models/user?view=table",
                    "type": "htmx"
                },
                {
                    "id": "admin_agents",
                    "label": "Агенты",
                    "icon": "robot",
                    "url": "/frontend/models/agent?view=table",
                    "type": "htmx"
                },
                {
                    "id": "admin_flows",
                    "label": "Flows",
                    "icon": "diagram-3",
                    "url": "/frontend/models/flow?view=table",
                    "type": "htmx"
                },
                {
                    "id": "admin_tasks",
                    "label": "Tasks",
                    "icon": "list-task",
                    "url": "/frontend/models/task?view=table",
                    "type": "htmx"
                },
                {
                    "id": "admin_companies",
                    "label": "Компании",
                    "icon": "building",
                    "url": "/frontend/admin/companies",
                    "type": "page"
                }
            ]
        }
    ]
    
    def get_router(self):
        from .router import router
        return router

