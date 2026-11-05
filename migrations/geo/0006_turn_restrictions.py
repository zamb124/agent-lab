"""Geo: запреты поворотов — geo_turn_restrictions + rows_restrictions.

``geo_turn_restrictions`` — канонический слой OSM-отношений
``type=restriction``: сырые ссылки from/to/via + ``via_lat/via_lng``,
проставляемые импортёром из ``geo_road_vertices`` после заливки; ``geom``
— GENERATED ALWAYS. ``rows_restrictions`` в ``geo_import_state`` —
счётчик активного поколения наряду с адресами/вершинами/рёбрами.
"""

depends_on = "0005_coverage_registry"


def upgrade(ctx):
    """Apply migration."""
    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_turn_restrictions (
            id bigserial PRIMARY KEY,
            generation integer NOT NULL DEFAULT 0,
            region varchar(64) NOT NULL DEFAULT '',
            osm_relation_id bigint NOT NULL,
            restriction varchar(64) NOT NULL,
            from_way bigint NOT NULL,
            to_way bigint NOT NULL,
            via_node bigint,
            via_way bigint,
            via_lat double precision,
            via_lng double precision,
            created_at timestamptz NOT NULL,
            geom geometry(Point,4326) GENERATED ALWAYS AS
                (CASE
                    WHEN via_lat IS NOT NULL AND via_lng IS NOT NULL
                    THEN ST_SetSRID(ST_MakePoint(via_lng, via_lat), 4326)
                 END) STORED,
            UNIQUE (osm_relation_id, generation)
        )
        """
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_turn_restrictions_generation_idx"
        " ON geo_turn_restrictions (generation)"
    )
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_turn_restrictions_geom_gist"
        " ON geo_turn_restrictions USING gist(geom)"
    )
    ctx.execute(
        "ALTER TABLE geo_import_state"
        " ADD COLUMN IF NOT EXISTS rows_restrictions integer NOT NULL DEFAULT 0"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute(
        "ALTER TABLE geo_import_state"
        " DROP COLUMN IF EXISTS rows_restrictions"
    )
    ctx.execute("DROP TABLE IF EXISTS geo_turn_restrictions")
