"""
Container - Dependency Injection контейнер.

Сервисы наследуют BaseContainer и добавляют свои сервисы через @lazy.
Контейнер доступен через request.app.state.container.

Пример:
    from core.container import BaseContainer, lazy
    from my_module import MyService

    class MyContainer(BaseContainer):
        @lazy
        def my_service(self):
            return MyService(repository=self.my_repository)
"""

from core.container.base import BaseContainer, lazy

__all__ = [
    "BaseContainer",
    "lazy",
]
