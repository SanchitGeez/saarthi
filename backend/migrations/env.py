from alembic import context
from sqlalchemy import create_engine

from config import Settings
from core.models import Base

if context.is_offline_mode():
    context.configure(
        url=Settings().database_url, target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(Settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
