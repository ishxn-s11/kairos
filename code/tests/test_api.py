"""Endpoint tests for the live engine API (code/serve_api.py).

Run: python3 -m pytest code/tests -q
These drive the real pipeline through Flask's test client — no network, no mocks.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

CODE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CODE_DIR.parent
sys.path.insert(0, str(CODE_DIR))

from serve_api import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def auth_client(tmp_path):
    previous = app.config.get("AUTH_DB_PATH")
    previous_url = app.config.get("AUTH_DATABASE_URL")
    previous_serverless = app.config.get("SERVERLESS")
    app.config["AUTH_DB_PATH"] = str(tmp_path / "accounts.sqlite3")
    app.config["AUTH_DATABASE_URL"] = ""
    app.config["SERVERLESS"] = False
    try:
        with app.test_client() as test_client:
            yield test_client
    finally:
        app.config["AUTH_DB_PATH"] = previous
        app.config["AUTH_DATABASE_URL"] = previous_url
        app.config["SERVERLESS"] = previous_serverless


def submitted_row(request_id: str) -> dict:
    with (REPO_ROOT / "output.csv").open(encoding="utf-8", newline="") as handle:
        return next(r for r in csv.DictReader(handle) if r["request_id"] == request_id)


def test_health_reports_the_full_dataset(client):
    body = client.get("/api/health").get_json()
    assert body["ok"] is True
    assert body["requests"] == 250
    assert body["model_calls"] >= 0
    assert body["cost_usd"] >= 0


def test_requests_index_carries_live_facts(client):
    rows = client.get("/api/requests").get_json()["requests"]
    assert len(rows) == 250
    row = next(r for r in rows if r["request_id"] == "request_26")
    assert row["request_date"]
    assert row["requested_amount"]
    assert row["home_currency"]


def test_no_overrides_reproduces_the_submitted_decision(client):
    body = client.post("/api/decide", json={"request_id": "request_26"}).get_json()
    assert body["changed"] == []
    assert body["modified"] == []
    assert body["decision"] == body["baseline"]

    submitted = submitted_row("request_26")
    assert body["decision"]["status"] == submitted["affordability_status"]
    assert body["decision"]["method"] == submitted["recommended_payment_method"]
    assert body["decision"]["plan"] == submitted["payment_plan"]
    assert body["decision"]["explanation"] == submitted["decision_explanation"]


def test_modified_amount_changes_the_verdict(client):
    baseline = client.post("/api/decide", json={"request_id": "request_26"}).get_json()
    bigger = client.post(
        "/api/decide", json={"request_id": "request_26", "requested_amount": 78000000}
    ).get_json()
    assert bigger["modified"] == ["requested_amount"]
    assert bigger["decision"]["status"] != baseline["decision"]["status"]
    assert "status" in bigger["changed"]
    assert "explanation" in bigger["changed"]


def test_smaller_amount_can_unlock_a_verdict(client):
    baseline = client.post("/api/decide", json={"request_id": "request_28"}).get_json()
    half = float(baseline["request"]["requested_amount"]) / 2
    smaller = client.post(
        "/api/decide", json={"request_id": "request_28", "requested_amount": half}
    ).get_json()
    rank = {"not_affordable": 0, "affordable_later": 1, "affordable_with_plan": 2, "affordable_now": 3}
    assert rank[smaller["decision"]["status"]] >= rank[baseline["decision"]["status"]]
    assert smaller["decision"] != baseline["decision"]


def test_modified_runs_are_deterministic(client):
    first = client.post("/api/decide", json={"request_id": "request_26", "requested_amount": 12345}).get_json()
    second = client.post("/api/decide", json={"request_id": "request_26", "requested_amount": 12345}).get_json()
    assert first["decision"] == second["decision"]


def test_date_and_partial_overrides_are_honoured(client):
    body = client.post(
        "/api/decide",
        json={"request_id": "request_29", "request_date": "2026-01-05", "allows_partial_payment": True},
    ).get_json()
    assert set(body["modified"]) == {"request_date", "allows_partial_payment"}
    assert body["request"]["request_date"] == "2026-01-05"
    assert body["request"]["allows_partial_payment"] is True


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"request_id": "request_999"}, 404),
        ({"request_id": ""}, 404),
        ({"request_id": "request_26", "requested_amount": "abc"}, 400),
        ({"request_id": "request_26", "requested_amount": -1}, 400),
        ({"request_id": "request_26", "request_date": "01/03/2026"}, 400),
    ],
)
def test_invalid_input_returns_a_clear_error(client, payload, code):
    res = client.post("/api/decide", json=payload)
    assert res.status_code == code
    assert res.get_json()["ok"] is False
    assert res.get_json()["error"]


def test_cors_and_no_store_headers(client):
    res = client.get("/api/health")
    assert res.headers["Access-Control-Allow-Origin"] == "*"
    assert res.headers["Cache-Control"] == "no-store"
    assert "Authorization" in res.headers["Access-Control-Allow-Headers"]


def test_account_registration_login_and_activity(auth_client):
    registration = auth_client.post(
        "/api/auth/register",
        json={"name": "Kai Test", "email": "kai@example.com", "password": "safe-pass-123"},
    )
    assert registration.status_code == 201
    body = registration.get_json()
    assert body["user"]["email"] == "kai@example.com"
    token = body["token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert auth_client.get("/api/auth/me", headers=headers).status_code == 200
    assert auth_client.post(
        "/api/decide", json={"request_id": "request_26"}, headers=headers
    ).status_code == 200
    actions = auth_client.get("/api/activity", headers=headers).get_json()["actions"]
    assert any(item["action"] == "decision_run" for item in actions)
    assert any(item["action"] == "register" for item in actions)

    assert auth_client.post("/api/auth/logout", headers=headers).status_code == 200
    assert auth_client.get("/api/auth/me", headers=headers).status_code == 401

    bad = auth_client.post(
        "/api/auth/login", json={"email": "kai@example.com", "password": "wrong-password"}
    )
    assert bad.status_code == 401
    login = auth_client.post(
        "/api/auth/login", json={"email": "kai@example.com", "password": "safe-pass-123"}
    )
    assert login.status_code == 200


def test_serverless_accounts_require_persistent_storage(auth_client):
    app.config["SERVERLESS"] = True
    response = auth_client.post(
        "/api/auth/register",
        json={"name": "Cloud Test", "email": "cloud@example.com", "password": "safe-pass-123"},
    )
    assert response.status_code == 503
    assert "DATABASE_URL" in response.get_json()["error"]
    # Demo decisions continue to work without account storage.
    assert auth_client.post("/api/decide", json={"request_id": "request_26"}).status_code == 200


def test_accounts_are_case_insensitive_and_activity_is_private(auth_client):
    first = auth_client.post(
        "/api/auth/register", json={"name": "First User", "email": "First@example.com", "password": "safe-pass-123"}
    ).get_json()
    duplicate = auth_client.post(
        "/api/auth/register", json={"name": "Duplicate User", "email": "FIRST@example.com", "password": "safe-pass-123"}
    )
    assert duplicate.status_code == 409
    first_headers = {"Authorization": f"Bearer {first['token']}"}
    auth_client.post("/api/decide", json={"request_id": "request_26"}, headers=first_headers)
    second = auth_client.post(
        "/api/auth/register", json={"name": "Second User", "email": "second@example.com", "password": "safe-pass-456"}
    ).get_json()
    second_headers = {"Authorization": f"Bearer {second['token']}"}
    assert auth_client.get("/api/auth/me", headers=second_headers).get_json()["stats"]["decisions"] == 0
    activity = auth_client.get("/api/activity", headers=second_headers).get_json()["actions"]
    assert all(item["action"] != "decision_run" for item in activity)
    login = auth_client.post("/api/auth/login", json={"email": "FIRST@example.com", "password": "safe-pass-123"})
    assert login.status_code == 200


@pytest.mark.parametrize("endpoint", ["register", "login"])
def test_auth_rejects_non_object_json(auth_client, endpoint):
    response = auth_client.post(f"/api/auth/{endpoint}", json=["invalid"])
    assert response.status_code == 400
