"""Live engine API for the KAIROS test bench.

A tiny Flask server that executes the REAL deterministic pipeline
(``code/buy_or_wait``) on demand, so the frontend test bench can run modified
requests — a new requested amount, a different request date, partial payment
toggled — instead of replaying the precomputed baseline.

Usage:
    python3 code/serve_api.py                  # http://127.0.0.1:8000
    python3 code/serve_api.py --port 8010 --debug

Endpoints:
    GET  /api/health    engine status, dataset size, model-call usage
    GET  /api/requests  every dataset request with facts (fills the overrides form)
    POST /api/decide    run the pipeline, optionally overridden:
                        {"request_id": "request_26", "requested_amount": 4200.5,
                         "request_date": "2026-03-01",
                         "desired_completion_date": "2026-05-01",
                         "allows_partial_payment": true}
                        → {decision, baseline, changed[], modified, request, usage}

The server binds loopback by default. Accounts use SQLite locally or PostgreSQL
when DATABASE_URL is configured. Override the
allowed origin with KAIROS_API_CORS (defaults to "*" for local dev).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sqlite3
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from flask import Flask, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "code"))

from buy_or_wait.forecast import fmt_amount  # noqa: E402
from buy_or_wait.loader import DataStore  # noqa: E402
from buy_or_wait.pipeline import analyze, analyze_from_ledger, decide  # noqa: E402
from buy_or_wait.usage import TRACKER  # noqa: E402
from buy_or_wait.freelancer import (  # noqa: E402
    Invoice,
    build_freelancer_ledger,
    variable_income_summary,
)
from buy_or_wait.report import build_report, _scenario_dict  # noqa: E402
from buy_or_wait.scenarios import ScenarioConfig, run_scenarios  # noqa: E402
from account_database import AccountDatabaseUnavailable, account_database  # noqa: E402

STORE = DataStore()
REQUESTS = {row.request_id: row for row in STORE.requests}
DECISION_FIELDS = ("amount", "status", "method", "plan", "earliest", "spending", "explanation")

app = Flask(__name__)
app.config["AUTH_DB_PATH"] = os.environ.get(
    "KAIROS_AUTH_DB", str(REPO_ROOT / ".kairos" / "accounts.sqlite3")
)
app.config["AUTH_DATABASE_URL"] = os.environ.get("KAIROS_AUTH_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
app.config["AUTH_SCHEMA_DATABASE_URL"] = os.environ.get("DATABASE_URL_UNPOOLED", "")
app.config["SERVERLESS"] = os.environ.get("VERCEL") == "1"
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db():
    return account_database(
        str(app.config["AUTH_DB_PATH"]),
        app.config["AUTH_DATABASE_URL"],
        schema_url=app.config["AUTH_SCHEMA_DATABASE_URL"],
        serverless=app.config["SERVERLESS"],
    )


@app.errorhandler(AccountDatabaseUnavailable)
def account_database_error(exc):
    app.logger.error("Account database unavailable")
    return jsonify({"ok": False, "error": str(exc)}), 503


def _public_user(row) -> dict:
    return {"id": row["id"], "name": row["name"], "email": row["email"], "created_at": row["created_at"]}


def _new_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    with _db() as conn:
        conn.execute(
            "INSERT INTO sessions(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)",
            (token_hash, user_id, now.isoformat(), (now + timedelta(days=30)).isoformat()),
        )
    return token


def _current_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    raw = header[7:].strip()
    if not raw:
        return None
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    with _db() as conn:
        row = conn.execute(
            """SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
               WHERE s.token_hash=? AND s.expires_at>?""",
            (token_hash, _now()),
        ).fetchone()
    return row


def _record_action(user_id: int | None, action: str, details: dict | None = None) -> None:
    if not user_id:
        return
    safe_details = json.dumps(details or {}, separators=(",", ":"), ensure_ascii=False)
    with _db() as conn:
        conn.execute(
            "INSERT INTO actions(user_id,action,details_json,created_at) VALUES(?,?,?,?)",
            (user_id, action, safe_details, _now()),
        )


@app.post("/api/auth/register")
def register_endpoint():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON body required"}), 400
    name = str(body.get("name") or "").strip()
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "")
    if len(name) < 2 or len(name) > 80:
        return jsonify({"ok": False, "error": "name must be between 2 and 80 characters"}), 400
    if not _EMAIL_RE.match(email) or len(email) > 254:
        return jsonify({"ok": False, "error": "enter a valid email address"}), 400
    if len(password) < 8 or len(password) > 256:
        return jsonify({"ok": False, "error": "password must be between 8 and 256 characters"}), 400
    try:
        with _db() as conn:
            cur = conn.execute(
                "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?) RETURNING id",
                (name, email, generate_password_hash(password), _now()),
            )
            user_id = cur.fetchone()["id"]
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "an account with this email already exists"}), 409
    token = _new_session(user_id)
    _record_action(user_id, "register")
    return jsonify({"ok": True, "token": token, "user": _public_user(row)}), 201


@app.post("/api/auth/login")
def login_endpoint():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON body required"}), 400
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "")
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE LOWER(email)=LOWER(?)", (email,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"ok": False, "error": "invalid email or password"}), 401
    token = _new_session(row["id"])
    _record_action(row["id"], "login")
    return jsonify({"ok": True, "token": token, "user": _public_user(row)})


@app.get("/api/auth/me")
def me_endpoint():
    user = _current_user()
    if user is None:
        return jsonify({"ok": False, "error": "authentication required"}), 401
    with _db() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM actions WHERE user_id=?", (user["id"],)).fetchone()["n"]
        decisions = conn.execute(
            "SELECT COUNT(*) AS n FROM actions WHERE user_id=? AND action='decision_run'", (user["id"],)
        ).fetchone()["n"]
    return jsonify({"ok": True, "user": _public_user(user), "stats": {"total_actions": total, "decisions": decisions}})


@app.post("/api/auth/logout")
def logout_endpoint():
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        token_hash = hashlib.sha256(header[7:].strip().encode("utf-8")).hexdigest()
        with _db() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
    return jsonify({"ok": True})


@app.get("/api/activity")
def activity_endpoint():
    user = _current_user()
    if user is None:
        return jsonify({"ok": False, "error": "authentication required"}), 401
    with _db() as conn:
        rows = conn.execute(
            "SELECT id,action,details_json,created_at FROM actions WHERE user_id=? ORDER BY id DESC LIMIT 50",
            (user["id"],),
        ).fetchall()
    actions = [
        {"id": row["id"], "action": row["action"], "details": json.loads(row["details_json"]), "created_at": row["created_at"]}
        for row in rows
    ]
    return jsonify({"ok": True, "actions": actions})


def _payload(decision) -> dict:
    return {
        "request_id": decision.request_id,
        "amount": fmt_amount(decision.amount_safe_to_pay),
        "status": decision.affordability_status,
        "method": decision.recommended_payment_method,
        "plan": decision.payment_plan,
        "earliest": decision.earliest_date_for_full_payment or "",
        "spending": decision.spending_changes_needed,
        "explanation": decision.decision_explanation,
    }


@lru_cache(maxsize=512)
def _run(request_id: str, amount: str, req_date: str, desired: str, partial):
    """Run the real pipeline (cached): identical overrides never re-execute."""
    base = REQUESTS[request_id]
    modified = replace(
        base,
        requested_amount=Decimal(amount) if amount else base.requested_amount,
        request_date=date.fromisoformat(req_date) if req_date else base.request_date,
        desired_completion_date=date.fromisoformat(desired) if desired else base.desired_completion_date,
        allows_partial_payment=base.allows_partial_payment if partial is None else partial,
    )
    return modified, decide(STORE, modified)


@app.get("/api/health")
def health():
    grand = TRACKER.grand_totals()
    return jsonify({
        "ok": True,
        "engine": "buy_or_wait — deterministic pipeline (code/buy_or_wait)",
        "requests": len(REQUESTS),
        "model_calls": grand["calls"],
        "cost_usd": round(grand["cost"], 6),
        "pid": os.getpid(),
    })


@app.get("/api/requests")
def requests_index():
    rows = []
    for row in STORE.requests:
        profile = STORE.profile_for(row.user_id)
        rows.append({
            "request_id": row.request_id,
            "user_id": row.user_id,
            "request_date": row.request_date.isoformat(),
            "requested_amount": str(row.requested_amount),
            "desired_completion_date": row.desired_completion_date.isoformat(),
            "allows_partial_payment": row.allows_partial_payment,
            "home_currency": profile.home_currency,
            "request_text": row.request_text,
        })
    return jsonify({"ok": True, "requests": rows})


@app.post("/api/decide")
def decide_endpoint():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON body required"}), 400

    request_id = str(body.get("request_id") or "").strip()
    if request_id not in REQUESTS:
        return jsonify({"ok": False, "error": f"unknown request_id: {request_id!r}"}), 404

    amount = ""
    if body.get("requested_amount") not in (None, ""):
        try:
            value = Decimal(str(body["requested_amount"]).replace(",", "").strip())
        except InvalidOperation:
            return jsonify({"ok": False, "error": f"requested_amount is not a number: {body['requested_amount']!r}"}), 400
        if value < 0:
            return jsonify({"ok": False, "error": "requested_amount must be >= 0"}), 400
        amount = str(value)

    dates = {}
    for key in ("request_date", "desired_completion_date"):
        raw = body.get(key)
        if raw in (None, ""):
            dates[key] = ""
            continue
        try:
            date.fromisoformat(str(raw))
        except ValueError:
            return jsonify({"ok": False, "error": f"{key} must be ISO YYYY-MM-DD: {raw!r}"}), 400
        dates[key] = str(raw)

    partial = body.get("allows_partial_payment")
    partial = None if partial is None else bool(partial)

    before = TRACKER.grand_totals()
    try:
        modified, decision = _run(request_id, amount, dates["request_date"], dates["desired_completion_date"], partial)
        _, baseline = _run(request_id, "", "", "", None)
    except Exception as exc:  # pragma: no cover - engine failure surfaces honestly
        return jsonify({"ok": False, "error": f"engine error: {exc}"}), 500
    after = TRACKER.grand_totals()

    live, base = _payload(decision), _payload(baseline)
    changed = [f for f in DECISION_FIELDS if live[f] != base[f]]
    base_row = REQUESTS[request_id]
    # the engine derives facts from the ledger, so report what it actually acted on
    effective = {
        "request_id": modified.request_id,
        "user_id": modified.user_id,
        "request_date": modified.request_date.isoformat(),
        "requested_amount": str(modified.requested_amount),
        "desired_completion_date": modified.desired_completion_date.isoformat(),
        "allows_partial_payment": modified.allows_partial_payment,
        "home_currency": STORE.profile_for(modified.user_id).home_currency,
    }
    modified_flags = [
        f for f in ("requested_amount", "request_date", "desired_completion_date", "allows_partial_payment")
        if getattr(modified, f) != getattr(base_row, f)
    ]

    user = _current_user()
    _record_action(
        user["id"] if user else None,
        "decision_run",
        {
            "request_id": modified.request_id,
            "status": live["status"],
            "method": live["method"],
            "modified": modified_flags,
        },
    )

    return jsonify({
        "ok": True,
        "decision": live,
        "baseline": base,
        "changed": changed,
        "modified": modified_flags,
        "request": effective,
        "usage": {
            "calls_for_this_run": after["calls"] - before["calls"],
            "tokens_total": after["in"] + after["out"],
            "cost_usd_total": round(after["cost"], 6),
        },
    })


def _d(value):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _dec(value, default=Decimal(0)):
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return default


def _effective_request(body):
    """Parse optional overrides. Returns (request, None) or (None, (msg, status))."""
    request_id = str(body.get("request_id") or "").strip()
    if request_id not in REQUESTS:
        return None, (f"unknown request_id: {request_id!r}", 404)
    base = REQUESTS[request_id]

    amount = base.requested_amount
    if body.get("requested_amount") not in (None, ""):
        try:
            value = Decimal(str(body["requested_amount"]).replace(",", "").strip())
        except InvalidOperation:
            return None, (f"requested_amount is not a number: {body['requested_amount']!r}", 400)
        if value < 0:
            return None, ("requested_amount must be >= 0", 400)
        amount = value

    req_date = base.request_date
    if body.get("request_date") not in (None, ""):
        try:
            req_date = date.fromisoformat(str(body["request_date"]))
        except ValueError:
            return None, (f"request_date must be ISO YYYY-MM-DD: {body['request_date']!r}", 400)

    desired = base.desired_completion_date
    if body.get("desired_completion_date") not in (None, ""):
        try:
            desired = date.fromisoformat(str(body["desired_completion_date"]))
        except ValueError:
            return None, (f"desired_completion_date must be ISO YYYY-MM-DD: {body['desired_completion_date']!r}", 400)

    partial = body.get("allows_partial_payment")
    partial = base.allows_partial_payment if partial is None else bool(partial)
    modified = replace(
        base,
        requested_amount=amount,
        request_date=req_date,
        desired_completion_date=desired,
        allows_partial_payment=partial,
    )
    return modified, None


def _parse_invoices(raw):
    if not raw:
        return []
    out = []
    for i, r in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(r, dict):
            continue
        out.append(
            Invoice(
                invoice_id=str(r.get("invoice_id") or f"inv_{i}"),
                client=str(r.get("client") or ""),
                amount=_dec(r.get("amount")),
                currency=str(r.get("currency") or ""),
                issue_date=_d(r.get("issue_date")),
                due_date=_d(r.get("due_date")),
                status=str(r.get("status") or "expected").strip().lower(),
                expected_payment_date=_d(r.get("expected_payment_date")),
                user_id=str(r.get("user_id") or ""),
            )
        )
    return out


def _scenario_cfg(body):
    return ScenarioConfig(
        delay_days=int(body.get("delay_days", 14)),
        shock_amount=_dec(body.get("shock_amount"), None),
        shock_date=_d(body.get("shock_date")),
    )


@app.post("/api/report")
def report_endpoint():
    """Explainable decision report (markdown + JSON) for one request."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON body required"}), 400
    modified, err = _effective_request(body)
    if err:
        return jsonify({"ok": False, "error": err[0]}), err[1]

    invoices = _parse_invoices(body.get("invoices"))
    want_scenarios = bool(body.get("scenarios"))
    home = STORE.profile_for(modified.user_id).home_currency

    if invoices or want_scenarios:
        base_ledger, at_risk = build_freelancer_ledger(STORE, modified, invoices)
        options = STORE.options_for(modified.request_id)
        analysis = analyze_from_ledger(base_ledger, options)
        inv_summary = variable_income_summary(invoices, home)
        scenario_report = (
            run_scenarios(base_ledger, at_risk, options, _scenario_cfg(body), baseline=analysis)
            if want_scenarios else None
        )
    else:
        analysis = analyze(STORE, modified)
        inv_summary = None
        scenario_report = None

    report = build_report(analysis, invoices_summary=inv_summary, scenario_report=scenario_report)
    user = _current_user()
    _record_action(
        user["id"] if user else None,
        "report_run",
        {"request_id": modified.request_id, "scenarios": want_scenarios, "invoices": len(invoices)},
    )
    return jsonify({"ok": True, "markdown": report.to_markdown(), "report": report.to_dict()})


@app.post("/api/scenarios")
def scenarios_endpoint():
    """Four uncertainty scenarios as separate simulator runs for one request."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON body required"}), 400
    modified, err = _effective_request(body)
    if err:
        return jsonify({"ok": False, "error": err[0]}), err[1]

    invoices = _parse_invoices(body.get("invoices"))
    base_ledger, at_risk = build_freelancer_ledger(STORE, modified, invoices)
    options = STORE.options_for(modified.request_id)
    baseline = analyze_from_ledger(base_ledger, options)
    report = run_scenarios(base_ledger, at_risk, options, _scenario_cfg(body), baseline=baseline)
    user = _current_user()
    _record_action(
        user["id"] if user else None,
        "scenarios_run",
        {"request_id": modified.request_id, "invoices": len(invoices)},
    )
    return jsonify({
        "ok": True,
        "request_id": modified.request_id,
        "invoices": variable_income_summary(invoices, STORE.profile_for(modified.user_id).home_currency),
        "scenarios": _scenario_dict(report),
        "usage": {"model_calls_for_run": TRACKER.grand_totals()["calls"]},
    })


@app.after_request
def add_headers(response):
    default_origin = request.host_url.rstrip("/") if app.config["SERVERLESS"] else "*"
    response.headers["Access-Control-Allow-Origin"] = os.environ.get("KAIROS_API_CORS", default_origin)
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Cache-Control"] = "no-store"
    return response


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="KAIROS live engine API (runs the real pipeline)")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: loopback only)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    print(f"KAIROS live engine — {len(REQUESTS)} dataset requests loaded (deterministic pipeline)")
    print(f"  GET  http://{args.host}:{args.port}/api/health")
    print(f"  GET  http://{args.host}:{args.port}/api/requests")
    print(f"  POST http://{args.host}:{args.port}/api/decide")
    print("  static test bench: http://127.0.0.1:8472/test.html")
    print("  next   test bench: http://127.0.0.1:8480/test/")
    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
