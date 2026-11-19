"""Добавить необязательное примечание к заказу."""

import sqlalchemy as sa
from alembic import op

revision = "8c2a9d4e71b0"
down_revision = "483fb1e80029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("customer_note", sa.String(255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("customer_note")
