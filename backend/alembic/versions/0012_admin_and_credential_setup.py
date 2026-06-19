"""admin role + post-Google credential setup (username, raw_password)

Revision ID: f0a1b2c3d4e5
Revises: e1f2a3b4c5d6
Create Date: 2026-06-19 00:00:00.000000

Adds the columns behind the refined auth flow:
- ``username``        unique handle picked after Google sign-up; login accepts
                      email OR username.
- ``raw_password``    plaintext password, stored so the single admin can view
                      what each user set (internal-tool requirement).
- ``credentials_set`` True once the user finished the post-Google setup step.
- ``is_admin``        admin can watch all users + read raw passwords.

Also relaxes ``hashed_password`` to NULLable — a brand-new Google sign-up
exists before the user has chosen a password.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0a1b2c3d4e5'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('username', sa.String(length=150), nullable=True))
    op.add_column('users', sa.Column('raw_password', sa.String(length=255), nullable=True))
    op.add_column(
        'users',
        sa.Column('credentials_set', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'users',
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('users', 'hashed_password', existing_type=sa.String(length=255), nullable=True)

    # Existing rows already have a password → treat them as fully set up.
    op.execute(
        "UPDATE users SET credentials_set = true WHERE hashed_password IS NOT NULL"
    )

    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.alter_column('users', 'hashed_password', existing_type=sa.String(length=255), nullable=False)
    op.drop_column('users', 'is_admin')
    op.drop_column('users', 'credentials_set')
    op.drop_column('users', 'raw_password')
    op.drop_column('users', 'username')
