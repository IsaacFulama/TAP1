from decimal import Decimal

import pytest

from tap.mobile import offline_sync


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def close(self):
        pass


class FakeConnection:
    def __init__(self, rows):
        self.fake_cursor = FakeCursor(rows)
        self.committed = False
        self.rolled_back = False

    def cursor(self, dictionary=False):
        return self.fake_cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def is_connected(self):
        return True

    def close(self):
        pass


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity", "not-a-number"])
def test_sync_rejects_non_positive_or_non_finite_amount(monkeypatch, amount):
    connection = FakeConnection([None])
    monkeypatch.setattr(offline_sync, "obtenir_connexion", lambda: connection)

    result = offline_sync.apply_sync_events([{
        "event_id": "event-invalid",
        "event_type": "record_payment",
        "device_id": "test-device",
        "payload": {"payment_id": 1, "amount": amount},
    }])[0]

    assert result["status"] == "failed"
    assert "montant" in result["message"].lower() or "invalide" in result["message"].lower()
    assert not any("UPDATE paiements" in query for query, _ in connection.fake_cursor.executed)


def test_sync_rejects_payment_above_remaining_balance(monkeypatch):
    connection = FakeConnection([
        None,
        {
            "statut_souscription": "Simple",
            "montant_total": Decimal("100.00"),
            "montant_paye": Decimal("90.00"),
        },
    ])
    monkeypatch.setattr(offline_sync, "obtenir_connexion", lambda: connection)

    result = offline_sync.apply_sync_events([{
        "event_id": "event-overpayment",
        "event_type": "record_payment",
        "device_id": "test-device",
        "payload": {"payment_id": 1, "amount": "20.00", "base_paid": "90.00"},
    }])[0]

    assert result["status"] == "conflict"
    assert "dépasse" in result["message"].lower()
    assert not any("UPDATE paiements" in query for query, _ in connection.fake_cursor.executed)


def test_sync_accepts_valid_payment(monkeypatch):
    connection = FakeConnection([
        None,
        {
            "statut_souscription": "Simple",
            "montant_total": Decimal("100.00"),
            "montant_paye": Decimal("50.00"),
        },
    ])
    monkeypatch.setattr(offline_sync, "obtenir_connexion", lambda: connection)
    monkeypatch.setattr(
        offline_sync,
        "_statuts_montant",
        lambda total, paid: ("Litigieux", "Partiel", total - paid),
    )

    result = offline_sync.apply_sync_events([{
        "event_id": "event-valid",
        "event_type": "record_payment",
        "device_id": "test-device",
        "payload": {"payment_id": 1, "amount": "25.00", "base_paid": "50.00"},
    }])[0]

    assert result["status"] == "synced"
    assert any("UPDATE paiements" in query for query, _ in connection.fake_cursor.executed)


def test_sync_rejects_even_small_overpayment(monkeypatch):
    connection = FakeConnection([
        None,
        {
            "statut_souscription": "Simple",
            "montant_total": Decimal("100.00"),
            "montant_paye": Decimal("90.00"),
        },
    ])
    monkeypatch.setattr(offline_sync, "obtenir_connexion", lambda: connection)

    result = offline_sync.apply_sync_events([{
        "event_id": "event-overpayment-cent",
        "event_type": "record_payment",
        "device_id": "test-device",
        "payload": {"payment_id": 1, "amount": "10.01", "base_paid": "90.00"},
    }])[0]

    assert result["status"] == "conflict"
    assert not any("UPDATE paiements" in query for query, _ in connection.fake_cursor.executed)
