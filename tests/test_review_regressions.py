from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pyotp
import pytest

from tests.conftest import csrf_token, login, step_up


@pytest.mark.parametrize("origin", ["null", "https://attacker.example", ""])
def test_login_rejects_untrusted_origins(client, origin):
    response = client.post(
        "/login", headers={"Origin": origin},
        data={"username": "admin", "password": "admin-pass"},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert "otp_session=" not in response.headers.get("set-cookie", "")


def test_login_accepts_same_origin(client):
    response = client.post(
        "/login", headers={"Origin": "http://testserver"},
        data={"username": "admin", "password": "admin-pass"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_login_accepts_localhost_alias_when_bound_to_loopback(client):
    response = client.post(
        "/login", headers={"Origin": "http://localhost:8000", "Host": "127.0.0.1:8000"},
        data={"username": "admin", "password": "admin-pass"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_step_up_budget_is_shared_across_endpoints_and_sessions(client, monkeypatch):
    from app.core import security

    login(client)
    token = csrf_token(client)
    for i in range(5):
        path = "/admin/step-up" if i % 2 else "/api/v1/me/step-up"
        assert client.post(path, data={"password": "wrong", "csrf_token": token}).status_code == 403
    # A new login/session must not reset the account's step-up budget.
    login(client)
    token = csrf_token(client)
    for path in ("/admin/step-up", "/api/v1/me/step-up"):
        assert client.post(path, data={"password": "admin-pass", "csrf_token": token}).status_code == 429
    now = security.time.time()
    monkeypatch.setattr(security.time, "time", lambda: now + 31)
    assert step_up(client).status_code == 200


@pytest.mark.parametrize("operation", ["member", "grant"])
def test_team_revocation_removes_access_immediately(client, operation):
    from app.core import database as db
    from app.core.security import hash_password

    admin = db.get_user_by_username("admin")
    user_id = db.create_user("review-user", hash_password("review-pass"))
    portal_id = db.create_otp_entry("review-portal", "Review Portal", pyotp.random_base32(), 30, admin["id"])
    team_id = db.create_team("review-team", admin["id"])
    db.add_team_member(team_id, user_id)
    db.create_team_portal_grant(team_id, portal_id, admin["id"], None)

    login(client, "review-user", "review-pass")
    user_cookie = client.cookies.get("otp_session")
    user_csrf = csrf_token(client, "/dashboard")
    assert client.post("/api/ui/portals/review-portal/otp", headers={"X-CSRF-Token": user_csrf}).status_code == 200

    path = "/admin/teams/review-team/members/remove" if operation == "member" else "/admin/teams/review-team/grants/review-portal/revoke"
    data = {"username": "review-user", "csrf_token": user_csrf}
    assert step_up(client, "review-pass").status_code == 200
    assert client.post(path, data=data, follow_redirects=False).status_code == 403

    login(client)
    data["csrf_token"] = csrf_token(client)
    assert client.post(path, data=data, follow_redirects=False).status_code == 428
    assert step_up(client).status_code == 200
    assert client.post(path, data={"username": "review-user"}, follow_redirects=False).status_code == 403
    assert client.post(path, data=data, follow_redirects=False).status_code == 303
    assert client.post(path, data=data, follow_redirects=False).status_code == 404

    client.cookies.clear()
    client.cookies.set("otp_session", user_cookie)
    assert client.get("/api/ui/portals").json()["portals"] == []
    assert client.post("/api/ui/portals/review-portal/otp", headers={"X-CSRF-Token": user_csrf}).status_code == 404
    action = "team.member.remove" if operation == "member" else "team.grant.revoke"
    assert any(event["action"] == action for event in db.list_audit_events())
    # An independent direct grant must still work after team access is removed.
    db.create_portal_grant(portal_id, user_id, admin["id"], "read", None)
    assert client.post("/api/ui/portals/review-portal/otp", headers={"X-CSRF-Token": user_csrf}).status_code == 200


def test_concurrent_client_rate_limit_and_window_reset(client):
    from app.core import database as db

    owner = db.get_user_by_username("admin")
    client_id = db.create_automation_client("concurrent-client", owner["id"], "test", None)
    for now in (1000, 1060):
        barrier = Barrier(12)

        def attempt(_):
            barrier.wait(timeout=10)
            return db.consume_client_rate_limit(client_id, now, 3)

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(attempt, range(12)))
        assert sum(results) == 3
        assert db.consume_client_rate_limit(client_id, now + 1, 3) is False


def test_concurrent_step_up_reservations_are_bounded(client):
    from app.core.database import reserve_step_up_attempt

    barrier = Barrier(12)

    def attempt(_):
        barrier.wait(timeout=10)
        return reserve_step_up_attempt("review-budget", 1000)

    with ThreadPoolExecutor(max_workers=12) as pool:
        assert sum(pool.map(attempt, range(12))) == 5
    assert reserve_step_up_attempt("review-budget", 1029) is False
    assert reserve_step_up_attempt("review-budget", 1030) is True
