"""Geo: светофоры — geo_traffic_signals + rows_signals.

``geo_traffic_signals`` — канонический слой OSM-нод
``highway=traffic_signals``: точка сигнала на графе. Роутинг читает пары
[въезжающее ребро, выезжающее ребро] через узел и добавляет штраф
``signal_delay_s[mode]`` секунд к стоимости транзита — механизм тот же,
что у рестрикций/барьеров, но cost — задержка, а не запрет. ``geom`` —
GENERATED ALWAYS. ``rows_signals`` в ``geo_import_state`` — счётчик
активного поколения.
"""

depends_on = "0007_barriers"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_traffic_signals (
            id bigserial PRIMARY KEY,
            generation integer NOT NULL DEFAULT 0,
            region varchar(64) NOT NULL DEFAULT '',
            osm_node_id bigint NOT NULL,
            lat double precision NOT NULL,
            lng double precision NOT NULL,
            created_at timestamptz NOT NULL,
            geom geometry(Point,4326) GENERATED ALWAYS AS
                (ST_SetSRID(ST_MakePoint(lng, lat), 4326)) STORED,
            UNIQUE (osm_node_id, generation)
        )
        """
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_traffic_signals_generation_idx"
        " ON geo_traffic_signals (generation)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_traffic_signals_geom_gist"
        " ON geo_traffic_signals USING gist(geom)"
    )
    ctx.execute(
        "ALTER TABLE geo_import_state"
        " ADD COLUMN IF NOT EXISTS rows_signals integer NOT NULL DEFAULT 0"
    )
