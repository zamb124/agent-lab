"""TaskIQ-воркер очереди ``geo`` (geo_worker)."""

from apps.geo.di import GeoDi
from apps.worker_manifest import wire_worker
from core.config import get_settings
from core.tasks.worker_bootstrap import build_worker

broker = wire_worker("geo")

worker_app = build_worker(
    broker,
    service_name="geo_worker",
    queue="geo",
    settings=get_settings(),
    di_class=GeoDi,
    database="geo_url",
)
