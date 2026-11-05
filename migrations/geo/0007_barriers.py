"""Geo: барьеры на путях — geo_barriers + rows_barriers.

``geo_barriers`` — канонический слой OSM-нод ``barrier=*``: тип барьера и
производные флаги блокировки по режимам движения (импортёр выводит их из
типа и access-тегов). Роутинг читает пары [въезд, выезд] через узел и
ставит штраф для режимов, которым барьер закрыт; концевые барьеры пар не
образуют — до тупика-шлагбаума доехать можно. ``geom`` — GENERATED
ALWAYS. ``rows_barriers`` в ``geo_import_state`` — счётчик активного
поколения наряду с адресами/вершинами/рёбрами/рестрикциями.
"""

depends_on = "0006_turn_restrictions"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_barriers (
            id bigserial PRIMARY KEY,
            generation integer NOT NULL DEFAULT 0,
            region varchar(64) NOT NULL DEFAULT '',
            osm_node_id bigint NOT NULL,
            barrier varchar(64) NOT NULL,
            block_car boolean NOT NULL DEFAULT false,
            block_foot boolean NOT NULL DEFAULT false,
            block_bike boolean NOT NULL DEFAULT false,
            block_scooter boolean NOT NULL DEFAULT false,
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
        "CREATE INDEX IF NOT EXISTS geo_barriers_generation_idx"
        " ON geo_barriers (generation)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_barriers_geom_gist"
        " ON geo_barriers USING gist(geom)"
    )
    ctx.execute(
        "ALTER TABLE geo_import_state"
        " ADD COLUMN IF NOT EXISTS rows_barriers integer NOT NULL DEFAULT 0"
    )
