"""Geo: адресный справочник, дорожный граф, состояние импорта (geo.mdc).

Таблицы global (``__global_model__``): тенант-данных нет. ``geom`` —
GENERATED ALWAYS из координат, в Oxyde-моделях не объявлен. Поколения
импорта сосуществуют до атомарного свопа ``current_generation``.
"""

depends_on = None


def upgrade(ctx):
    """Apply migration."""
    ctx.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    ctx.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    ctx.execute("CREATE EXTENSION IF NOT EXISTS pgrouting")

    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_addresses (
            id bigserial PRIMARY KEY,
            osm_type text NOT NULL,
            osm_id bigint NOT NULL,
            display_name text NOT NULL,
            city text NOT NULL DEFAULT '',
            street text NOT NULL DEFAULT '',
            housenumber text NOT NULL DEFAULT '',
            postcode text NOT NULL DEFAULT '',
            lat double precision NOT NULL,
            lng double precision NOT NULL,
            generation integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL,
            geom geometry(Point,4326) GENERATED ALWAYS AS
                (ST_SetSRID(ST_MakePoint(lng, lat), 4326)) STORED,
            UNIQUE (osm_type, osm_id, generation)
        )
        """
    )
    ctx.execute("CREATE INDEX IF NOT EXISTS geo_addresses_geom_gist ON geo_addresses USING gist(geom)")
    ctx.execute("CREATE INDEX IF NOT EXISTS geo_addresses_generation_idx ON geo_addresses (generation)")
    ctx.execute(
        "CREATE INDEX IF NOT EXISTS geo_addresses_name_trgm ON geo_addresses USING gin(display_name gin_trgm_ops)"
    )

    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_road_vertices (
            id bigserial PRIMARY KEY,
            node_id bigint NOT NULL,
            lat double precision NOT NULL,
            lng double precision NOT NULL,
            generation integer NOT NULL DEFAULT 0,
            geom geometry(Point,4326) GENERATED ALWAYS AS
                (ST_SetSRID(ST_MakePoint(lng, lat), 4326)) STORED,
            UNIQUE (node_id, generation)
        )
        """
    )
    ctx.execute("CREATE INDEX IF NOT EXISTS geo_road_vertices_geom_gist ON geo_road_vertices USING gist(geom)")
    ctx.execute("CREATE INDEX IF NOT EXISTS geo_road_vertices_generation_idx ON geo_road_vertices (generation)")

    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_road_edges (
            id bigserial PRIMARY KEY,
            source bigint NOT NULL,
            target bigint NOT NULL,
            src_lat double precision NOT NULL,
            src_lng double precision NOT NULL,
            dst_lat double precision NOT NULL,
            dst_lng double precision NOT NULL,
            length_m double precision NOT NULL,
            car_cost double precision NOT NULL,
            car_reverse_cost double precision NOT NULL,
            foot_cost double precision NOT NULL,
            foot_reverse_cost double precision NOT NULL,
            oneway smallint NOT NULL DEFAULT 0,
            highway text NOT NULL DEFAULT '',
            name text NOT NULL DEFAULT '',
            osm_way_id bigint NOT NULL,
            generation integer NOT NULL DEFAULT 0,
            geom geometry(LineString,4326) GENERATED ALWAYS AS
                (ST_MakeLine(
                    ST_MakePoint(src_lng, src_lat),
                    ST_MakePoint(dst_lng, dst_lat)
                )) STORED
        )
        """
    )
    ctx.execute("CREATE INDEX IF NOT EXISTS geo_road_edges_source_idx ON geo_road_edges (source)")
    ctx.execute("CREATE INDEX IF NOT EXISTS geo_road_edges_target_idx ON geo_road_edges (target)")
    ctx.execute("CREATE INDEX IF NOT EXISTS geo_road_edges_generation_idx ON geo_road_edges (generation)")
    ctx.execute("CREATE INDEX IF NOT EXISTS geo_road_edges_geom_gist ON geo_road_edges USING gist(geom)")

    ctx.execute(
        """
        CREATE TABLE IF NOT EXISTS geo_import_state (
            id integer PRIMARY KEY,
            current_generation integer NOT NULL DEFAULT 0,
            status varchar(32) NOT NULL DEFAULT 'idle',
            source_name text NOT NULL DEFAULT '',
            source_modified_at timestamptz,
            rows_addresses integer NOT NULL DEFAULT 0,
            rows_vertices integer NOT NULL DEFAULT 0,
            rows_edges integer NOT NULL DEFAULT 0,
            last_error text NOT NULL DEFAULT '',
            started_at timestamptz,
            finished_at timestamptz,
            updated_at timestamptz NOT NULL
        )
        """
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("DROP TABLE IF EXISTS geo_road_edges")
    ctx.execute("DROP TABLE IF EXISTS geo_road_vertices")
    ctx.execute("DROP TABLE IF EXISTS geo_addresses")
    ctx.execute("DROP TABLE IF EXISTS geo_import_state")
