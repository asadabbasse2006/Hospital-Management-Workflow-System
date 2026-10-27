"""change lab result abnormal flag to boolean

Revision ID: 9bbf5eb48f70
Revises: 5972d77ec586
Create Date: 2026-10-25 22:45:37.615568
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



revision: str = '9bbf5eb48f70'
down_revision: Union[str, Sequence[str], None] = '5972d77ec586'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reject unexpected values rather than silently converting them.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM lab_results
                WHERE abnormal_flag IS NOT NULL
                  AND lower(btrim(abnormal_flag)) NOT IN (
                      'true', 'false', 't', 'f',
                      'yes', 'no', 'y', 'n', '1', '0'
                  )
            ) THEN
                RAISE EXCEPTION
                    'Unexpected abnormal_flag values; inspect lab_results before migrating';
            END IF;
        END
        $$;
    """)

    op.alter_column(
        "lab_results",
        "abnormal_flag",
        existing_type=sa.VARCHAR(length=30),
        type_=sa.Boolean(),
        existing_nullable=True,
        postgresql_using="""
            CASE
                WHEN abnormal_flag IS NULL THEN NULL
                WHEN lower(btrim(abnormal_flag)) IN ('true', 't', 'yes', 'y', '1')
                    THEN TRUE
                ELSE FALSE
            END
        """,
    )


def downgrade() -> None:
    op.alter_column(
        "lab_results",
        "abnormal_flag",
        existing_type=sa.Boolean(),
        type_=sa.VARCHAR(length=30),
        existing_nullable=True,
        postgresql_using="abnormal_flag::varchar(30)",
    )