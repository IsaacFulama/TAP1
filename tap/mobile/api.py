from __future__ import annotations

import hmac
import os
from decimal import Decimal, InvalidOperation
from html import escape

from flask import Flask, jsonify, request

from tap.mobile.offline_sync import apply_sync_events
from tap.mobile.portal_service import get_portal_data, sign_portal_payment
from tap.infrastructure.database.repository import ajouter_paiement_complementaire


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/api/mobile/health")
    def health():
        return jsonify({"status": "ok", "service": "tap-mobile", "offline_sync": True})

    @app.get("/api/portal/<token>/data")
    def portal_data(token: str):
        data = get_portal_data(token)
        if data is None:
            return jsonify({"error": "Lien invalide ou expiré."}), 404
        return jsonify(data)

    @app.post("/api/portal/<token>/payments/<int:payment_id>/sign")
    def portal_sign(token: str, payment_id: int):
        body = request.get_json(silent=True) or {}
        ok, message = sign_portal_payment(
            token, payment_id, body.get("signature", ""), bool(body.get("consent")),
            request.remote_addr or "", request.headers.get("User-Agent", ""),
        )
        return jsonify({"status": "signed" if ok else "error", "message": message}), 200 if ok else 400

    @app.post("/api/mobile/sync")
    def sync():
        expected = os.getenv("TAP_MOBILE_API_KEY", "").strip()
        provided = request.headers.get("X-TAP-Mobile-Key", "")
        if not expected or not hmac.compare_digest(expected, provided):
            return jsonify({"error": "Authentification mobile requise."}), 401
        body = request.get_json(silent=True) or {}
        events = body.get("events", [])
        if not isinstance(events, list) or len(events) > 100:
            return jsonify({"error": "Lot d'événements invalide."}), 400
        return jsonify({"results": apply_sync_events(events)})

    @app.post("/api/mobile/payments/<int:payment_id>/record")
    def record_payment(payment_id: int):
        expected = os.getenv("TAP_MOBILE_API_KEY", "").strip()
        provided = request.headers.get("X-TAP-Mobile-Key", "")
        if not expected or not hmac.compare_digest(expected, provided):
            return jsonify({"error": "Authentification mobile requise."}), 401
        body = request.get_json(silent=True) or {}
        try:
            amount = Decimal(str(body.get("amount", 0)))
            if not amount.is_finite() or amount <= Decimal("0"):
                raise ValueError
        except (InvalidOperation, TypeError, ValueError):
            return jsonify({"error": "Le montant doit être un nombre fini strictement positif."}), 400
        ok, message = ajouter_paiement_complementaire(payment_id, float(amount))
        return jsonify({"status": "ok" if ok else "error", "message": message}), 200 if ok else 400

    @app.get("/portal/<token>")
    def portal_page(token: str):
        return _portal_html(token)

    @app.get("/portal/<token>/payments/<int:payment_id>/receipt")
    def portal_receipt(token: str, payment_id: int):
        data = get_portal_data(token)
        if not data:
            return "Lien invalide ou expiré.", 404
        payment = next((p for p in data["payments"] if int(p["id"]) == payment_id), None)
        if not payment:
            return "Paiement introuvable.", 404
        return _receipt_html(data["tenant"], payment)

    return app


def _portal_html(token: str) -> str:
    safe_token = escape(token, quote=True)
    page = """<!doctype html>
<html lang='fr'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Portail locataire TAP</title><style>
body{{margin:0;background:#f6f1e8;color:#2b2118;font-family:Arial,sans-serif}}main{{max-width:760px;margin:auto;padding:16px}}.card{{background:#fffaf1;border:1px solid #d7c3a4;border-radius:14px;padding:18px;box-shadow:0 6px 20px #2f22181c}}h1{{font-size:24px}}.payment{{background:white;border:1px solid #eadcc8;border-radius:10px;margin:10px 0;padding:14px}}.row{{display:flex;justify-content:space-between;gap:12px;padding:6px 0}}.muted{{color:#6f604f}}.ok{{color:#2e7d32}}.warn{{color:#c45b12}}button{{width:100%;border:0;border-radius:8px;padding:13px;margin-top:10px;background:#b99057;color:#130d07;font-weight:700;font-size:15px}}#signBox{{display:none;background:white;border:1px solid #d7c3a4;border-radius:10px;padding:12px;margin-top:14px}}canvas{{width:100%;height:190px;background:#fff;border:2px dashed #b99057;border-radius:8px;touch-action:none}}#message{{font-weight:700;margin-top:8px}}@media(max-width:520px){{.row{{display:block}}.row strong{{display:block;margin-top:4px}}}}
</style></head><body><main><section class='card'><h1>Portail locataire TAP</h1><div id='app'>Chargement...</div></section></main><script>
const token='__TOKEN__';let selected=null,dirty=false;const app=document.getElementById('app');
function text(tag,value,cls=''){{const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e;}}
function load(){{fetch('/api/portal/'+token+'/data').then(r=>r.json()).then(data=>{{if(data.error)throw Error(data.error);app.replaceChildren(text('h2',data.tenant.prenom+' '+data.tenant.nom));data.payments.forEach(p=>{{const card=document.createElement('article');card.className='payment';[['Mois',p.mois],['Total',p.montant_total+' '+p.devise],['Payé',p.montant_paye+' '+p.devise],['Reste',p.reste_a_payer+' '+p.devise],['Statut',p.statut]].forEach(([label,value])=>{{const row=document.createElement('div');row.className='row';row.append(text('span',label,'muted'),text('strong',value,p.statut==='En règle'?'ok':'warn'));card.append(row);}});const receipt=document.createElement('button');receipt.textContent='Voir / imprimer le reçu';receipt.onclick=()=>window.open('/portal/'+token+'/payments/'+p.id+'/receipt','_blank');card.append(receipt);if(!p.est_signe){{const sign=document.createElement('button');sign.textContent='Signer ce paiement';sign.onclick=()=>openSign(p.id);card.append(sign);}}else card.append(text('div','✓ Reçu déjà signé','ok'));app.append(card);}});}}).catch(e=>app.replaceChildren(text('p',e.message,'warn')));}}
function openSign(id){{selected=id;dirty=false;document.getElementById('signBox').style.display='block';document.getElementById('message').textContent='';resize();window.scrollTo(0,document.body.scrollHeight);}}
const box=document.createElement('div');box.id='signBox';box.innerHTML='<h3>Signature tactile</h3><canvas id="pad"></canvas><button id="clear" type="button">Effacer</button><label><input id="consent" type="checkbox"> Je confirme ce reçu.</label><button id="send" type="button">Signer et envoyer</button><div id="message"></div>';app.append(box);const canvas=document.getElementById('pad'),ctx=canvas.getContext('2d');let drawing=false;
function resize(){{const r=canvas.getBoundingClientRect(),ratio=devicePixelRatio||1;canvas.width=r.width*ratio;canvas.height=r.height*ratio;ctx.setTransform(ratio,0,0,ratio,0,0);ctx.lineWidth=3;ctx.lineCap='round';ctx.strokeStyle='#1d1710';}}
function point(e){{const r=canvas.getBoundingClientRect();return [e.clientX-r.left,e.clientY-r.top];}}canvas.onpointerdown=e=>{{drawing=true;dirty=true;canvas.setPointerCapture(e.pointerId);const p=point(e);ctx.beginPath();ctx.moveTo(...p);}};canvas.onpointermove=e=>{{if(drawing){{const p=point(e);ctx.lineTo(...p);ctx.stroke();}}}};canvas.onpointerup=()=>drawing=false;canvas.onpointercancel=()=>drawing=false;document.getElementById('clear').onclick=()=>{{ctx.clearRect(0,0,canvas.width,canvas.height);dirty=false;}};document.getElementById('send').onclick=()=>{{const m=document.getElementById('message');if(!selected||!dirty||!document.getElementById('consent').checked){{m.textContent='Signez et confirmez votre consentement.';return;}}m.textContent='Envoi...';fetch('/api/portal/'+token+'/payments/'+selected+'/sign',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{consent:true,signature:canvas.toDataURL('image/png')}})}}).then(r=>r.json()).then(d=>{{m.textContent=d.message;if(d.status==='signed')load();}}).catch(()=>m.textContent='Connexion impossible. Réessayez lorsque le réseau revient.');}};window.onresize=resize;load();
</script></body></html>"""
    return page.replace("__TOKEN__", safe_token)


def _receipt_html(tenant: dict, payment: dict) -> str:
    values = {
        "nom": f"{tenant.get('prenom', '')} {tenant.get('nom', '')}".strip(),
        "mois": payment.get("mois", ""),
        "total": f"{payment.get('montant_total', '')} {payment.get('devise', '')}",
        "paye": f"{payment.get('montant_paye', '')} {payment.get('devise', '')}",
        "reste": f"{payment.get('reste_a_payer', '')} {payment.get('devise', '')}",
        "statut": payment.get("statut", ""),
    }
    safe = {key: escape(str(value)) for key, value in values.items()}
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Reçu TAP</title><style>body{{font-family:Arial;max-width:680px;margin:auto;padding:20px;color:#2b2118}}.receipt{{border:2px solid #d7c3a4;padding:24px;border-radius:12px}}.row{{display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid #eadcc8}}button{{width:100%;padding:14px;margin-top:20px}}@media print{{button{{display:none}}}}</style></head><body><section class='receipt'><h1>Reçu de paiement</h1><div class='row'><span>Locataire</span><strong>{safe['nom']}</strong></div><div class='row'><span>Mois</span><strong>{safe['mois']}</strong></div><div class='row'><span>Total</span><strong>{safe['total']}</strong></div><div class='row'><span>Payé</span><strong>{safe['paye']}</strong></div><div class='row'><span>Reste</span><strong>{safe['reste']}</strong></div><div class='row'><span>Statut</span><strong>{safe['statut']}</strong></div><button onclick='window.print()'>Imprimer / enregistrer en PDF</button></section></body></html>"""
