"""Восстановить unique (company_id, namespace, source, target, type) на relationships.

``0002_auto`` случайно снёс ``relationships_company_id_namespace_source_entity_id_target_entity_id_relationship_type_idx``,
хотя ``Relationship.Meta.unique_together`` декларирует констрейнт. Без него
``op_relationships_create`` ловил ``UniqueViolationError`` впустую и дубликат
связи создавался (200 вместо 409).

Перед созданием индекса удаляем дубли: каноничной считается самая ранняя
строка (min ``relationship_id`` стабилен при равных ``created_at``).
"""

depends_on = "0002_auto"


def upgrade(ctx):
    """Dedupe по (company_id, namespace, source, target, type) → unique index обратно."""
    ctx.execute(
        """
        DELETE FROM relationships a
        USING relationships b
        WHERE a.company_id = b.company_id
          AND a.namespace = b.namespace
          AND a.source_entity_id = b.source_entity_id
          AND a.target_entity_id = b.target_entity_id
          AND a.relationship_type = b.relationship_type
          AND (a.created_at, a.relationship_id) > (b.created_at, b.relationship_id)
        """
    )
    ctx.create_index("relationships", {
        'name': 'relationships_company_id_namespace_source_entity_id_target_entity_id_relationship_type_idx',
        'fields': [
            'company_id',
            'namespace',
            'source_entity_id',
            'target_entity_id',
            'relationship_type',
        ],
        'unique': True,
        'method': None,
    })


def downgrade(ctx):
    """Откат: снять unique index (состояние после 0002_auto)."""
    ctx.drop_index(
        "relationships",
        "relationships_company_id_namespace_source_entity_id_target_entity_id_relationship_type_idx",
    )
