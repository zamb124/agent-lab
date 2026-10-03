"""Auto-generated migration.

Created: 2026-09-26 13:15:00
"""

depends_on = "0001_initial"


def upgrade(ctx):
    """Apply migration."""
    ctx.drop_index("work_queues", "work_queues_company_id_slug_idx")
    ctx.alter_column("work_item_comments", "role", column_type={
    'kind': 'text'
})
    ctx.alter_column("work_items", "kind", column_type={
    'kind': 'text'
})
    ctx.alter_column("work_items", "state", column_type={
    'kind': 'text'
})
    ctx.alter_column("work_items", "priority", column_type={
    'kind': 'text'
})


def downgrade(ctx):
    """Revert migration."""
    ctx.create_index("work_queues", {
    'name': 'work_queues_company_id_slug_idx',
    'fields': [
        'company_id',
        'slug'
    ],
    'unique': True,
    'method': None
})
