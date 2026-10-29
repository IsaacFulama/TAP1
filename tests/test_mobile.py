from pathlib import Path

import pytest

from tap.mobile.api import _portal_html, create_app
from tap.mobile.offline_queue import OfflineQueue
from tap.mobile.security import hash_access_token, tokens_match


def test_mobile_health_and_authentication():
    client = create_app().test_client()

    assert client.get("/api/mobile/health").get_json()["status"] == "ok"
    assert client.post("/api/mobile/sync", json={"events": []}).status_code == 401


def test_portal_html_escapes_token():
    client = create_app().test_client()

    page = _portal_html("a'><b>bad")

    assert "<b>bad" not in page


def test_token_hash_is_verifiable():
    token = "temporary-token"

    assert tokens_match(token, hash_access_token(token))
    assert not tokens_match("other-token", hash_access_token(token))


def test_offline_queue_is_durable(tmp_path: Path):
    queue = OfflineQueue(tmp_path / "offline.sqlite")
    event_id = queue.enqueue(
        "record_payment",
        {"payment_id": 12, "amount": 25, "base_paid": 100},
        "device-test",
    )

    assert queue.pending()[0]["event_id"] == event_id
    queue.mark_result(event_id, "conflict", {"message": "changed"})
    assert queue.pending() == []


@pytest.mark.parametrize("amount", [-1, 0, "NaN", "Infinity", "-Infinity", "not-a-number"])
def test_direct_mobile_payment_rejects_invalid_amount(monkeypatch, amount):
    monkeypatch.setenv("TAP_MOBILE_API_KEY", "test-secret")
    called = []
    monkeypatch.setattr(
        "tap.mobile.api.ajouter_paiement_complementaire",
        lambda payment_id, value: called.append((payment_id, value)) or (True, "ok"),
    )
    client = create_app().test_client()

    response = client.post(
        "/api/mobile/payments/1/record",
        json={"amount": amount},
        headers={"X-TAP-Mobile-Key": "test-secret"},
    )

    assert response.status_code == 400
    assert called == []
