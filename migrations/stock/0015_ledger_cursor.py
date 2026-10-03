"""``entry_no`` журнала на курсор полосы — таблица счётчика больше не нужна.

``stock_ledger_counters`` дублировал ровно то, что уже умеет
``lane_cursors``: строка, заблокированная на всю транзакцию, с
монотонным счётчиком без пропусков. Теперь ``entry_no`` выделяется
курсором ``stock_ledger`` в той же ``lane_cursors``, что держит и
полосы складов — один примитив сериализации вместо двух таблиц.

Upgrade переносит значения счётчиков в курсоры
(``last_seq = next_entry_no - 1``, следующий вызов вернёт старое
``next_entry_no``). Downgrade восстанавливает таблицу и заливает её
обратно из курсоров.
"""

depends_on = "0014_packaging_into_uom"


def upgrade(ctx):
    ctx.execute(
        "INSERT INTO lane_cursors (lane_id, company_id, last_seq, updated_at)"
        " SELECT 'stock_ledger:' || company_id || ':entry_no', company_id,"
        " next_entry_no - 1, now() FROM stock_ledger_counters"
        " ON CONFLICT (lane_id) DO UPDATE SET"
        " last_seq = GREATEST(lane_cursors.last_seq, EXCLUDED.last_seq)"
    )
    ctx.drop_table("stock_ledger_counters")


def downgrade(ctx):
    ctx.create_table(
        "stock_ledger_counters",
        fields=[
            {
                'name': 'company_id',
                'column_type': {'kind': 'string', 'length': 100},
                'db_type': None, 'nullable': False, 'primary_key': True,
                'unique': False, 'default': None, 'auto_increment': False,
                'max_length': 100, 'max_digits': None, 'decimal_places': None,
            },
            {
                'name': 'next_entry_no',
                'column_type': {'kind': 'integer', 'bits': 64},
                'db_type': None, 'nullable': False, 'primary_key': False,
                'unique': False, 'default': 1, 'auto_increment': False,
                'max_length': None, 'max_digits': None, 'decimal_places': None,
            },
        ],
    )
    ctx.execute(
        "INSERT INTO stock_ledger_counters (company_id, next_entry_no)"
        " SELECT company_id, last_seq + 1 FROM lane_cursors"
        " WHERE lane_id LIKE 'stock_ledger:%'"
    )
