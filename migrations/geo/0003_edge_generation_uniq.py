"""Geo: уникальность ребра внутри поколения импорта.

Импорт заливает рёбра батчами по ходу парсинга; повторный заход в то же
поколение (рестарт воркера, retry задачи) не должен плодить дубли — как у
``geo_addresses``/``geo_road_vertices``, рёбра получают ``UNIQUE`` и
``ON CONFLICT DO NOTHING`` на вставке.
"""

depends_on = "0002_light_modes"


def upgrade(ctx):
    """Apply migration."""
    # Частичные поколения упавших импортов могли оставить дубли рёбер.
    ctx.execute(
        "DELETE FROM geo_road_edges a USING geo_road_edges b "
        "WHERE a.ctid > b.ctid AND a.generation = b.generation "
        "AND a.osm_way_id = b.osm_way_id AND a.source = b.source "
        "AND a.target = b.target"
    )
    ctx.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS geo_road_edges_gen_seg_uniq "
        "ON geo_road_edges (generation, osm_way_id, source, target)"
    )


def downgrade(ctx):
    """Rollback migration."""
    ctx.execute("DROP INDEX IF EXISTS geo_road_edges_gen_seg_uniq")
