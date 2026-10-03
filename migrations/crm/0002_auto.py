"""Auto-generated migration.

Created: 2026-09-26 13:15:00
"""

depends_on = "0001_initial"


def upgrade(ctx):
    """Apply migration."""
    ctx.drop_index("entity_types", "entity_types_company_id_namespace_type_id_idx")
    ctx.drop_index("relationship_types", "relationship_types_company_id_type_id_idx")
    ctx.drop_index("relationships", "relationships_company_id_namespace_source_entity_id_target_entity_id_relationship_type_idx")
    ctx.alter_column("entity_types", "entity_type_row_id", default="''")
    ctx.alter_column("relationship_types", "relationship_type_row_id", default="''")
    ctx.create_index("entity_types", {
    'name': 'entity_types_type_id_idx',
    'fields': [
        'type_id'
    ],
    'unique': False,
    'method': None
})
    ctx.create_index("relationship_types", {
    'name': 'relationship_types_type_id_idx',
    'fields': [
        'type_id'
    ],
    'unique': False,
    'method': None
})


def downgrade(ctx):
    """Revert migration."""
    ctx.drop_index("relationship_types", "relationship_types_type_id_idx")
    ctx.drop_index("entity_types", "entity_types_type_id_idx")
    ctx.create_index("relationships", {
    'name': 'relationships_company_id_namespace_source_entity_id_target_entity_id_relationship_type_idx',
    'fields': [
        'company_id',
        'namespace',
        'source_entity_id',
        'target_entity_id',
        'relationship_type'
    ],
    'unique': True,
    'method': None
})
    ctx.create_index("relationship_types", {
    'name': 'relationship_types_company_id_type_id_idx',
    'fields': [
        'company_id',
        'type_id'
    ],
    'unique': True,
    'method': None
})
    ctx.create_index("entity_types", {
    'name': 'entity_types_company_id_namespace_type_id_idx',
    'fields': [
        'company_id',
        'namespace',
        'type_id'
    ],
    'unique': True,
    'method': None
})
