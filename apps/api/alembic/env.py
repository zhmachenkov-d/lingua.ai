from alembic import context
from sqlalchemy import create_engine

from app.db.config import get_database_url, to_sqlalchemy_url
from app.models import Base

target_metadata = Base.metadata


def run_migrations_online() -> None:
    url = context.config.attributes.get("database_url") or get_database_url()
    engine = create_engine(to_sqlalchemy_url(url))
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


run_migrations_online()
