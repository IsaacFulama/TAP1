from tap.infrastructure.database import migrations


class FakeCursor:
    def __init__(self):
        self.queries = []
        self._fetchone = (0, "varchar")

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return [(7, "not-a-month"), (8, "also-invalid")]

    def close(self):
        pass


class FakeConnection:
    def __init__(self):
        self.fake_cursor = FakeCursor()
        self.closed = False

    def is_connected(self):
        return True

    def cursor(self):
        return self.fake_cursor

    def close(self):
        self.closed = True


def test_invalid_months_abort_migration_without_rewriting_data(monkeypatch, capsys):
    connection = FakeConnection()
    monkeypatch.setattr(migrations, "obtenir_connexion", lambda: connection)

    migrations.migrer_mois_vers_date()

    sql = [query for query, _ in connection.fake_cursor.queries]
    assert not any(query.startswith("UPDATE paiements SET mois") for query in sql)
    assert not any(query.startswith("ALTER TABLE paiements MODIFY COLUMN mois") for query in sql)
    assert "2 valeur(s) invalide(s)" in capsys.readouterr().out
