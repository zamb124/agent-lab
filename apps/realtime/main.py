"""
Realtime bus — единственный HTTP-peer Centrifugo.

Порт: 8025
БД: platform_realtime
"""

from apps.realtime.api import get_api_router
from apps.realtime.config import RealtimeSettings
from apps.realtime.di import RealtimeDi, command_deadline_sweeper
from core.app import create_service_app
from core.config import get_settings

app = create_service_app(
    "realtime",
    RealtimeSettings,
    RealtimeDi,
    database="realtime_url",
    lifecycle=(command_deadline_sweeper,),
    routers=[get_api_router()],
    title="Realtime Bus",
    description="Durable-лог PlatformEvent и единственный HTTP-peer Centrifugo",
    api_version="v1",
)


if __name__ == "__main__":
    from core.app.server import serve

    serve("realtime", "apps.realtime.main:app", get_settings())
