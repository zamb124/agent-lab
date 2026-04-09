"""crm_entities: tsvector колонка + GIN индекс + триггер для полнотекстового поиска

Revision ID: crm_0012
Revises: crm_0011
Create Date: 2026-04-09
"""

from typing import Sequence, Union

from alembic import op

revision: str = "crm_0012"
down_revision: Union[str, None] = "crm_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MANAGED_TABLES = {"crm_entities"}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE crm_entities
        ADD COLUMN IF NOT EXISTS search_vector tsvector;
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_crm_entities_fts
        ON crm_entities USING gin(search_vector);
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION crm_entities_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('simple', coalesce(NEW.name, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(NEW.description, '')), 'B') ||
                setweight(to_tsvector('simple', coalesce(
                    (SELECT string_agg(value::text, ' ')
                     FROM jsonb_each_text(coalesce(NEW.attributes, '{}'::jsonb))),
                    ''
                )), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_crm_entities_search_vector ON crm_entities;
        CREATE TRIGGER trg_crm_entities_search_vector
        BEFORE INSERT OR UPDATE OF name, description, attributes
        ON crm_entities
        FOR EACH ROW
        EXECUTE FUNCTION crm_entities_search_vector_update();
    """)

    op.execute("""
        UPDATE crm_entities SET search_vector =
            setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(description, '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(
                (SELECT string_agg(value::text, ' ')
                 FROM jsonb_each_text(coalesce(attributes, '{}'::jsonb))),
                ''
            )), 'C');
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_crm_entities_search_vector ON crm_entities;")
    op.execute("DROP FUNCTION IF EXISTS crm_entities_search_vector_update();")
    op.execute("DROP INDEX IF EXISTS ix_crm_entities_fts;")
    op.execute("ALTER TABLE crm_entities DROP COLUMN IF EXISTS search_vector;")
