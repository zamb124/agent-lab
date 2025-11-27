"""
Container - Dependency Injection контейнер.

Сервисы наследуют BaseContainer и добавляют свои сервисы через @lazy.
Контейнер доступен через request.app.state.container.

Пример:
    from core.container import BaseContainer, lazy
    
    class MyContainer(BaseContainer):
        @lazy
        def my_service(self):
            from my_module import MyService
            return MyService(repository=self.my_repository)
"""

from core.container.base import BaseContainer, lazy

__all__ = [
    "BaseContainer",
    "lazy",
]

