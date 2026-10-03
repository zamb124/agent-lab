"""Восстановить unique (company_id, slug) на work_queues.

``0002_auto`` случайно снёс ``work_queues_company_id_slug_idx``: генератор
не сматчил ``unique_together`` модели на колонку ``slug``
(``db_column="slug"`` у поля ``work_queue_slug``). Без констрейнта
параллельные ``create_queue`` создавали дубли, а ``by_slug`` падал с
``MultipleObjectsReturned``.

Перед созданием индекса удаляем дубли: каноничной считается самая ранняя
строка (min ``work_queue_id`` стабилен при равных ``created_at``).
Членство очереди живёт в OpenFGA по ``work_queue_id``, FK на таблицу нет.
"""

depends_on = "0002_auto"


def upgrade(ctx):
    """Dedupe по (company_id, slug) → unique index обратно."""
    ctx.execute(
        """
        DELETE FROM work_queues a
        USING work_queues b
        WHERE a.company_id = b.company_id
          AND a.slug = b.slug
          AND (a.created_at, a.work_queue_id) > (b.created_at, b.work_queue_id)
        """
    )
    ctx.create_index("work_queues", {
        'name': 'work_queues_company_id_slug_idx',
        'fields': [
            'company_id',
            'slug',
        ],
        'unique': True,
        'method': None,
    })


def downgrade(ctx):
    """Откат: снять unique index (состояние после 0002_auto)."""
    ctx.drop_index("work_queues", "work_queues_company_id_slug_idx")
