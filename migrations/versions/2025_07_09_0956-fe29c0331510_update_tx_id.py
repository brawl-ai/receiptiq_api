"""Update tx id

Revision ID: fe29c0331510
Revises: c9e5d3b49587
Create Date: 2025-07-09 09:56:06.179960

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fe29c0331510'
down_revision: Union[str, None] = 'c9e5d3b49587'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_unique_constraint(None, 'audit_logs', ['id'])
    op.create_unique_constraint(None, 'data_values', ['id'])
    op.create_unique_constraint(None, 'fields', ['id'])
    op.create_unique_constraint(None, 'login_attempts', ['id'])
    op.create_unique_constraint(None, 'password_reset_tokens', ['id'])
    op.alter_column('payments', 'amount',
               existing_type=sa.REAL(),
               type_=sa.Float(precision=15, decimal_return_scale=2),
               existing_nullable=False)
    op.alter_column('payments', 'fees',
               existing_type=sa.REAL(),
               type_=sa.Float(precision=15, decimal_return_scale=2),
               existing_nullable=True)
    op.alter_column('payments', 'requested_amount',
               existing_type=sa.REAL(),
               type_=sa.Float(precision=15, decimal_return_scale=2),
               existing_nullable=True)
    op.create_unique_constraint(None, 'payments', ['id'])
    op.create_unique_constraint(None, 'permissions', ['id'])
    op.create_unique_constraint(None, 'projects', ['id'])
    op.create_unique_constraint(None, 'receipts', ['id'])
    op.create_unique_constraint(None, 'refresh_tokens', ['id'])
    op.create_unique_constraint(None, 'revoked_tokens', ['id'])
    op.alter_column('subscription_plans', 'price',
               existing_type=sa.REAL(),
               type_=sa.Float(precision=10, decimal_return_scale=2),
               existing_nullable=False)
    op.create_unique_constraint(None, 'subscription_plans', ['id'])
    op.create_unique_constraint(None, 'subscriptions', ['id'])
    op.create_unique_constraint(None, 'users', ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'users', type_='unique')
    op.drop_constraint(None, 'subscriptions', type_='unique')
    op.drop_constraint(None, 'subscription_plans', type_='unique')
    op.alter_column('subscription_plans', 'price',
               existing_type=sa.Float(precision=10, decimal_return_scale=2),
               type_=sa.REAL(),
               existing_nullable=False)
    op.drop_constraint(None, 'revoked_tokens', type_='unique')
    op.drop_constraint(None, 'refresh_tokens', type_='unique')
    op.drop_constraint(None, 'receipts', type_='unique')
    op.drop_constraint(None, 'projects', type_='unique')
    op.drop_constraint(None, 'permissions', type_='unique')
    op.drop_constraint(None, 'payments', type_='unique')
    op.alter_column('payments', 'requested_amount',
               existing_type=sa.Float(precision=15, decimal_return_scale=2),
               type_=sa.REAL(),
               existing_nullable=True)
    op.alter_column('payments', 'fees',
               existing_type=sa.Float(precision=15, decimal_return_scale=2),
               type_=sa.REAL(),
               existing_nullable=True)
    op.alter_column('payments', 'amount',
               existing_type=sa.Float(precision=15, decimal_return_scale=2),
               type_=sa.REAL(),
               existing_nullable=False)
    op.drop_constraint(None, 'password_reset_tokens', type_='unique')
    op.drop_constraint(None, 'login_attempts', type_='unique')
    op.drop_constraint(None, 'fields', type_='unique')
    op.drop_constraint(None, 'data_values', type_='unique')
    op.drop_constraint(None, 'audit_logs', type_='unique')
    # ### end Alembic commands ###
