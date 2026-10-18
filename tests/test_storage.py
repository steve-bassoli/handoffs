from app.storage import Database, one


def test_migration_is_repeatable_and_data_survives(tmp_path):
    path = tmp_path / 'test.sqlite'
    db = Database(path)
    db.migrate()
    with db.write() as connection:
        connection.exec_driver_sql("INSERT INTO users VALUES ('a','A','A')")
    db.engine.dispose()
    restarted = Database(path)
    restarted.migrate()
    with restarted.engine.connect() as connection:
        assert one(connection, 'SELECT * FROM users')['id'] == 'a'
        assert one(connection, 'SELECT version_num FROM alembic_version')['version_num'] == '004'
    restarted.engine.dispose()
