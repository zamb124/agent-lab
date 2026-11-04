"""Geo Worker (очередь ``geo``).

OSM-импорт справочника и дорожного графа: bootstrap при старте на пустом
справочнике и регулярный resync по расписанию scheduler.

Запуск: taskiq worker apps.geo.worker:worker_app
"""

# ruff: noqa: E402, I001

from apps.geo.config import GeoSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.files.urls import resolve_files_route_segment, set_files_route_segment
from core.tasks.logging_init import setup_worker_logging_early

_settings = GeoSettings.model_validate(
    load_merged_config(service_name="geo_worker", silent=True)
)
setup_worker_logging_early("geo_worker", logging_config=_settings.logging)
set_settings(_settings)
set_files_route_segment(resolve_files_route_segment("geo_worker"))

from apps.geo.di import GeoDi
from apps.geo.services.osm_import_service import OsmImportService
from apps.worker_manifest import wire_worker
from core.di import recipe
from core.tasks.worker_bootstrap import build_worker

broker = wire_worker("geo")


async def ensure_import_bootstrapped(osm_import_service: OsmImportService) -> None:
    """Пустой справочник при старте воркера → первый импорт без ожидания cron."""
    _ = await osm_import_service.ensure_bootstrapped()


worker_app = build_worker(
    broker,
    service_name="geo_worker",
    queue="geo",
    settings=_settings,
    di_class=GeoDi,
    database="geo_url",
    lifecycle=(recipe(ensure_import_bootstrapped),),
)

__all__ = ["worker_app"]
