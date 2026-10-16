from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event


def one(connection, sql, params=()):
    result = connection.exec_driver_sql(sql, params).mappings().first()
    return dict(result) if result else None


def all_rows(connection, sql, params=()):
    return [dict(row) for row in connection.exec_driver_sql(sql, params).mappings()]


class Database:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            'sqlite:///' + self.path.as_posix(),
            connect_args={'check_same_thread': False, 'timeout': 10},
        )

        @event.listens_for(self.engine, 'connect')
        def configure(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')

    def migrate(self):
        config = Config()
        config.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'migrations'))
        with self.engine.begin() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, 'head')

    @contextmanager
    def write(self):
        with self.engine.connect() as connection:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
