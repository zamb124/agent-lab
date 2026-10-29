"""Каталог desktop toolkits не хранится в базе flows.

Created: 2026-10-28
"""

depends_on = "0002_auto"


def upgrade(ctx):
    """Apply migration."""
    ctx.drop_table("agent_toolkits")


def downgrade(ctx):
    """Revert migration."""
    pass
