from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from mysql.connector import Error

from tap.infrastructure.database.connection import obtenir_connexion
from tap.infrastructure.database.repository import _statuts_montant


def apply_sync_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for event in events:
        event_id = str(event.get("event_id", ""))
        if not event_id or not event.get("event_type"):
            results.append({"event_id": event_id, "status": "failed", "message": "Événement invalide."})
            continue
        results.append(_apply_one(event))
    return results


def _apply_one(event: dict[str, Any]) -> dict[str, Any]:
    event_id = str(event["event_id"])
    payload = event.get("payload") or {}
    conn = None
    cursor = None
    try:
        conn = obtenir_connexion()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status FROM offline_sync_events WHERE event_id = %s", (event_id,))
        existing = cursor.fetchone()
        if existing and existing["status"] == "synced":
            return {"event_id": event_id, "status": "synced", "idempotent": True}
        if event["event_type"] != "record_payment":
            return _record_result(conn, cursor, event, "failed", "Type d'événement non supporté.")

        try:
            payment_id = int(payload["payment_id"])
            amount = Decimal(str(payload["amount"]))
            base_paid = Decimal(str(payload["base_paid"])) if "base_paid" in payload else None
        except (InvalidOperation, TypeError, ValueError, KeyError):
            return _record_result(conn, cursor, event, "failed", "Identifiant ou montant invalide.")

        if payment_id <= 0 or not amount.is_finite() or amount <= Decimal("0"):
            return _record_result(conn, cursor, event, "failed", "Le montant doit être un nombre fini strictement positif.")
        if base_paid is not None and (not base_paid.is_finite() or base_paid < Decimal("0")):
            return _record_result(conn, cursor, event, "failed", "Le montant de référence est invalide.")

        cursor.execute(
            "SELECT statut_souscription, montant_total, montant_paye FROM paiements WHERE id = %s FOR UPDATE",
            (payment_id,),
        )
        row = cursor.fetchone()
        if not row:
            return _record_result(conn, cursor, event, "conflict", "Paiement introuvable.")
        if row["statut_souscription"] == "Spécial":
            return _record_result(conn, cursor, event, "conflict", "Les paiements spéciaux doivent être synchronisés depuis le desktop.")

        current_paid = Decimal(str(row["montant_paye"]))
        if not current_paid.is_finite() or current_paid < Decimal("0"):
            return _record_result(conn, cursor, event, "conflict", "Le montant déjà payé est invalide.")
        if base_paid is None:
            base_paid = current_paid
        if abs(current_paid - base_paid) > Decimal("0.01"):
            return _record_result(conn, cursor, event, "conflict", "Le paiement a changé sur le serveur.")

        total = Decimal(str(row["montant_total"]))
        if not total.is_finite() or total < Decimal("0"):
            return _record_result(conn, cursor, event, "conflict", "Le total du paiement est invalide.")
        if amount > total - current_paid:
            return _record_result(conn, cursor, event, "conflict", "Le montant dépasse le solde restant.")

        new_paid = current_paid + amount
        status, payment_status, remaining = _statuts_montant(total, new_paid)
        cursor.execute(
            "UPDATE paiements SET montant_paye=%s, reste_a_payer=%s, statut=%s, statut_paiement=%s WHERE id=%s",
            (float(new_paid), float(remaining), status, payment_status, payment_id),
        )
        return _record_result(conn, cursor, event, "synced", "Paiement synchronisé.")
    except (Error, InvalidOperation, TypeError, ValueError, KeyError) as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return {"event_id": event_id, "status": "failed", "message": f"Événement invalide ou erreur de base de données: {type(exc).__name__}"}
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None and conn.is_connected():
            conn.close()


def _record_result(conn, cursor, event, status: str, message: str) -> dict[str, Any]:
    cursor.execute(
        """
        INSERT INTO offline_sync_events
            (event_id, device_id, event_type, payload_json, status, conflict_json)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE status = VALUES(status), conflict_json = VALUES(conflict_json), synced_at = NOW()
        """,
        (str(event["event_id"]), str(event.get("device_id", "")), str(event["event_type"]),
         json.dumps(event.get("payload", {}), ensure_ascii=False), status,
         message if status == "conflict" else None),
    )
    conn.commit()
    return {"event_id": str(event["event_id"]), "status": status, "message": message}
