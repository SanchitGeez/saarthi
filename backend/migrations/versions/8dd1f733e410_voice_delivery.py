"""Voice ownership lease and delivered message status.

Revision ID: 8dd1f733e410
Revises: 62b4ebea1318
"""

import sqlalchemy as sa
from alembic import op

revision = "8dd1f733e410"
down_revision = "62b4ebea1318"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conversations", sa.Column("voice_token", sa.Uuid(), nullable=True))
    op.add_column("conversations", sa.Column("voice_expires_at", sa.DateTime(timezone=True)))
    op.add_column(
        "messages",
        sa.Column("delivery_status", sa.String(16), server_default="complete", nullable=False),
    )
    op.add_column(
        "messages", sa.Column("kind", sa.String(16), server_default="reply", nullable=False)
    )
    op.create_check_constraint("message_kind", "messages", "kind IN ('reply', 'voice_notice')")
    op.drop_index("one_greeting", table_name="messages")
    op.create_index(
        "one_greeting",
        "messages",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("role = 'assistant' AND reply_to_id IS NULL AND kind = 'reply'"),
    )
    op.create_check_constraint(
        "message_delivery_status", "messages", "delivery_status IN ('complete', 'interrupted')"
    )


def downgrade():
    # Downgrading loses delivered operational notices, never user/agent replies.
    op.execute("DELETE FROM messages WHERE kind = 'voice_notice'")
    op.drop_index("one_greeting", table_name="messages")
    op.create_index(
        "one_greeting",
        "messages",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("role = 'assistant' AND reply_to_id IS NULL"),
    )
    op.drop_constraint("message_kind", "messages")
    op.drop_column("messages", "kind")
    op.drop_constraint("message_delivery_status", "messages")
    op.drop_column("messages", "delivery_status")
    op.drop_column("conversations", "voice_expires_at")
    op.drop_column("conversations", "voice_token")
