"""Auto-generated migration.

Created: 2026-09-25 20:31:06
"""

depends_on = "0002_lanes"


def upgrade(ctx):
    """Apply migration."""
    ctx.add_column("stock_locations", {
    'name': 'allow_negative',
    'column_type': {
        'kind': 'boolean'
    },
    'db_type': None,
    'nullable': False,
    'primary_key': False,
    'unique': False,
    'default': 'FALSE',
    'auto_increment': False,
    'max_length': None,
    'max_digits': None,
    'decimal_places': None
})


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_column("stock_locations", "allow_negative")
