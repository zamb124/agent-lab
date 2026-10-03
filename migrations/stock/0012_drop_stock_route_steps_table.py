"""Плечи маршрута встраиваются в stock_routes.steps (JSONB).

Шаг маршрута — часть агрегата без своего жизненного цикла: отдельная
таблица давала только join при каждом чтении маршрута. Теперь одна
строка маршрута содержит упорядоченный список плеч
[{sequence, operation_type_id, source_location_id, dest_location_id}].

Данные переносятся: шаги агрегируются в JSONB-массив по sequence.

Created: 2026-09-26
"""

depends_on = "0011_auto"

_STEP_FIELDS = "sequence, operation_type_id, source_location_id, dest_location_id"


def upgrade(ctx):
    """Apply migration."""
    ctx.add_column("stock_routes", {
        'name': 'steps',
        'column_type': {
            'kind': 'json_binary'
        },
        'db_type': 'JSONB',
        'nullable': False,
        'primary_key': False,
        'unique': False,
        'default': "'[]'::jsonb",
        'auto_increment': False,
        'max_length': None,
        'max_digits': None,
        'decimal_places': None
    })
    ctx.execute(
        "UPDATE stock_routes r SET steps = COALESCE(("
        "SELECT jsonb_agg(jsonb_build_object("
        "'sequence', s.sequence, "
        "'operation_type_id', s.operation_type_id, "
        "'source_location_id', s.source_location_id, "
        "'dest_location_id', s.dest_location_id"
        ") ORDER BY s.sequence, s.step_id) "
        "FROM stock_route_steps s "
        "WHERE s.route_id = r.route_id AND s.company_id = r.company_id"
        "), '[]'::jsonb)"
    )
    ctx.drop_table("stock_route_steps")


def downgrade(ctx):
    """Revert migration."""
    ctx.create_table(
        "stock_route_steps",
        fields=[
                       {
                           'name': 'step_id',
                           'column_type': {
                               'kind': 'string',
                               'length': 64
                           },
                           'db_type': None,
                           'nullable': False,
                           'primary_key': True,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': 64,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'company_id',
                           'column_type': {
                               'kind': 'string',
                               'length': 100
                           },
                           'db_type': None,
                           'nullable': False,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': 100,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'route_id',
                           'column_type': {
                               'kind': 'string',
                               'length': 64
                           },
                           'db_type': None,
                           'nullable': False,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': 64,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'sequence',
                           'column_type': {
                               'kind': 'big_integer'
                           },
                           'db_type': None,
                           'nullable': False,
                           'primary_key': False,
                           'unique': False,
                           'default': '10',
                           'auto_increment': False,
                           'max_length': None,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'operation_type_id',
                           'column_type': {
                               'kind': 'string',
                               'length': 64
                           },
                           'db_type': None,
                           'nullable': False,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': 64,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'source_location_id',
                           'column_type': {
                               'kind': 'string',
                               'length': 64
                           },
                           'db_type': None,
                           'nullable': True,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': 64,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'dest_location_id',
                           'column_type': {
                               'kind': 'string',
                               'length': 64
                           },
                           'db_type': None,
                           'nullable': True,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': 64,
                           'max_digits': None,
                           'decimal_places': None
                       },
                       {
                           'name': 'created_at',
                           'column_type': {
                               'kind': 'date_time'
                           },
                           'db_type': None,
                           'nullable': False,
                           'primary_key': False,
                           'unique': False,
                           'default': None,
                           'auto_increment': False,
                           'max_length': None,
                           'max_digits': None,
                           'decimal_places': None
                       }
                   ],
        indexes=[
                         {
                             'name': 'stock_route_steps_company_id_route_id_idx',
                             'fields': [
                                 'company_id',
                                 'route_id'
                             ],
                             'unique': False,
                             'method': None
                         }
                     ],
    )
    # Шаги назад в таблицу из JSONB
    ctx.execute(
        "INSERT INTO stock_route_steps (step_id, company_id, route_id, "
        "sequence, operation_type_id, source_location_id, "
        "dest_location_id, created_at) "
        "SELECT 'rts_' || r.route_id || '_' || s.ord::text, r.company_id, "
        "r.route_id, (s.step ->> 'sequence')::bigint, "
        "s.step ->> 'operation_type_id', s.step ->> 'source_location_id', "
        "s.step ->> 'dest_location_id', r.created_at "
        "FROM stock_routes r "
        "CROSS JOIN LATERAL jsonb_array_elements(r.steps) "
        "WITH ORDINALITY AS s(step, ord)"
    )
    ctx.drop_column("stock_routes", "steps")

