"""search_vector: включить tags в tsvector, триггер на UPDATE OF tags

Revision ID: crm_0015
Revises: crm_0014
Create Date: 2026-04-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "crm_0015"
down_revision: Union[str, None] = "crm_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION crm_entities_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('simple', coalesce(NEW.name, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(NEW.description, '')), 'B') ||
                setweight(to_tsvector('simple', coalesce(
                    (SELECT string_agg(value::text, ' ')
                     FROM jsonb_each_text(coalesce(NEW.attributes, '{}'::jsonb))),
                    ''
                )), 'C') ||
                setweight(to_tsvector('simple', coalesce(array_to_string(NEW.tags, ' '), '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        "DROP TRIGGER IF EXISTS trg_crm_entities_search_vector ON crm_entities;"
    )
    op.execute(
        """
        CREATE TRIGGER trg_crm_entities_search_vector
        BEFORE INSERT OR UPDATE OF name, description, attributes, tags
        ON crm_entities
        FOR EACH ROW
        EXECUTE FUNCTION crm_entities_search_vector_update();
        """
    )

    op.execute(
        """
        UPDATE crm_entities SET search_vector =
            setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(description, '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(
                (SELECT string_agg(value::text, ' ')
                 FROM jsonb_each_text(coalesce(attributes, '{}'::jsonb))),
                ''
            )), 'C') ||
            setweight(to_tsvector('simple', coalesce(array_to_string(tags, ' '), '')), 'C');
        """
    )


def downgrade() -> None:
    op.execute(
        """
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
        """
    )

    op.execute(
        "DROP TRIGGER IF EXISTS trg_crm_entities_search_vector ON crm_entities;"
    )
    op.execute(
        """
        CREATE TRIGGER trg_crm_entities_search_vector
        BEFORE INSERT OR UPDATE OF name, description, attributes
        ON crm_entities
        FOR EACH ROW
        EXECUTE FUNCTION crm_entities_search_vector_update();
        """
    )

    op.execute(
        """
        UPDATE crm_entities SET search_vector =
            setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(description, '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(
                (SELECT string_agg(value::text, ' ')
                 FROM jsonb_each_text(coalesce(attributes, '{}'::jsonb))),
                ''
            )), 'C');
        """
    )
