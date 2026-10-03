"""Путевой лист волны и порядок обхода строк исполнения.

``stock_waves.stops`` — порядок остановок рейса (``transfer_id`` в
очереди объезда); ``stock_move_lines.stop_order`` — позиция накладной
строки в этом рейсе. ``sequence`` строки уже означает обход ячеек и
теперь заполняется из ``pick_sequence`` рабочей локации — очередь
ТСД читается как «приоритет → остановка → ячейка».
"""

depends_on = "0015_ledger_cursor"


def upgrade(ctx):
    ctx.add_column("stock_waves", {
        'name': 'stops',
        'column_type': {'kind': 'json_binary'},
        'db_type': 'JSONB',
        'nullable': False,
        'primary_key': False,
        'unique': False,
        'default': "'[]'::jsonb",
        'auto_increment': False,
        'max_length': None,
        'max_digits': None,
        'decimal_places': None,
    })
    ctx.add_column("stock_move_lines", {
        'name': 'stop_order',
        'column_type': {'kind': 'big_integer'},
        'db_type': None,
        'nullable': False,
        'primary_key': False,
        'unique': False,
        'default': '0',
        'auto_increment': False,
        'max_length': None,
        'max_digits': None,
        'decimal_places': None,
    })
    ctx.create_index("stock_move_lines", {
        'name': 'stock_move_lines_queue_idx',
        'fields': ['company_id', 'warehouse_id', 'state', 'stop_order', 'sequence'],
        'unique': False, 'method': None, 'where': None,
    })


def downgrade(ctx):
    ctx.drop_index("stock_move_lines", "stock_move_lines_queue_idx")
    ctx.drop_column("stock_move_lines", "stop_order")
    ctx.drop_column("stock_waves", "stops")
