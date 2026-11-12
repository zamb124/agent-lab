"""Auto-generated migration.

Created: 2026-11-12 01:31:25
"""

depends_on = "0017_auto"


def upgrade(ctx):
    """Apply migration."""
    ctx.create_enum_type('scan_flow_enum', [
    'receive',
    'move',
    'putaway',
    'pick',
    'pack',
    'ship',
    'container_move',
    'count',
    'inquiry'
])
    ctx.add_column("stock_operation_types", {
    'name': 'scan_flow',
    'column_type': {
        'kind': 'enum',
        'name': 'scan_flow_enum',
        'values': [
            'receive',
            'move',
            'putaway',
            'pick',
            'pack',
            'ship',
            'container_move',
            'count',
            'inquiry'
        ]
    },
    'db_type': None,
    'nullable': True,
    'primary_key': False,
    'unique': False,
    'default': None,
    'auto_increment': False,
    'max_length': 32,
    'max_digits': None,
    'decimal_places': None
})


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_column("stock_operation_types", "scan_flow")
    ctx.drop_enum_type('scan_flow_enum')
