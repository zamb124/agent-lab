"""Auto-generated migration.

Created: 2026-09-26 13:15:00
"""

depends_on = "0007_create_stock_reorder_rules_table"


def upgrade(ctx):
    """Apply migration."""
    ctx.create_index("stock_move_lines", {
    'name': 'stock_move_lines_company_id_wave_id_state_idx',
    'fields': [
        'company_id',
        'wave_id',
        'state'
    ],
    'unique': False,
    'method': None
})
    ctx.create_index("stock_moves", {
    'name': 'stock_moves_company_id_origin_document_id_state_idx',
    'fields': [
        'company_id',
        'origin_document_id',
        'state'
    ],
    'unique': False,
    'method': None
})
    ctx.create_index("stock_moves", {
    'name': 'stock_moves_company_id_move_origin_id_idx',
    'fields': [
        'company_id',
        'move_origin_id'
    ],
    'unique': False,
    'method': None
})


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_index("stock_moves", "stock_moves_company_id_move_origin_id_idx")
    ctx.drop_index("stock_moves", "stock_moves_company_id_origin_document_id_state_idx")
    ctx.drop_index("stock_move_lines", "stock_move_lines_company_id_wave_id_state_idx")
