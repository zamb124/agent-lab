"""Geo: ``bike_cost``/``scooter_cost`` пары — гибридные лёгкие режимы.

Строки старых поколений получают ``-1`` (непроходимо) — корректно: до
переимпорта лёгких режимов в данных нет. Стоимость, как и у car/foot, —
в секундах на направление.
"""

depends_on = "0001_initial"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        "ALTER TABLE geo_road_edges "
        "ADD COLUMN IF NOT EXISTS bike_cost double precision NOT NULL DEFAULT -1, "
        "ADD COLUMN IF NOT EXISTS bike_reverse_cost double precision NOT NULL DEFAULT -1, "
        "ADD COLUMN IF NOT EXISTS scooter_cost double precision NOT NULL DEFAULT -1, "
        "ADD COLUMN IF NOT EXISTS scooter_reverse_cost double precision NOT NULL DEFAULT -1"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute(
        "ALTER TABLE geo_road_edges "
        "DROP COLUMN IF EXISTS bike_cost, "
        "DROP COLUMN IF EXISTS bike_reverse_cost, "
        "DROP COLUMN IF EXISTS scooter_cost, "
        "DROP COLUMN IF EXISTS scooter_reverse_cost"
    )
