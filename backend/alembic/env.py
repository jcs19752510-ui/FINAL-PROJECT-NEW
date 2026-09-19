from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import settings
from app.db.session import Base
from app.models.code_submission import CodeSubmission  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.consent import Consent  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.deletion_request import DeletionRequest  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.interview import Interview  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.rubric_template import RubricTemplate  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.transcript import Transcript  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.user import User  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
