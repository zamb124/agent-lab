"""Auto-generated migration.

Created: 2026-11-15 22:23:48
"""

depends_on = "0003_drop_agent_toolkits"


def upgrade(ctx):
    """Apply migration."""
    ctx.alter_column("evaluation_cases", "description", column_type={
    'kind': 'text'
}, db_type='TEXT')


def downgrade(ctx):
    """Revert migration."""
    pass
