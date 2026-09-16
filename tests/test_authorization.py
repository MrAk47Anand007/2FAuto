import pyotp


def test_user_dashboard_is_deny_by_default_until_granted(client):
    from tests.conftest import csrf_token, login, step_up

    login(client)
    assert step_up(client).status_code == 200
    portal_response = client.post(
        "/admin/portals",
        data={
            "portal_name": "restricted-portal",
            "display_name": "Restricted Portal",
            "secret": pyotp.random_base32(),
            "period": "30",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    assert portal_response.status_code in (302, 303)

    user_response = client.post(
        "/admin/users",
        data={
            "username": "restricted-user",
            "password": "restricted-pass",
            "role": "user",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    assert user_response.status_code in (302, 303)

    client.post(
        "/logout",
        data={"csrf_token": csrf_token(client, "/dashboard")},
        follow_redirects=False,
    )
    login(client, "restricted-user", "restricted-pass")
    assert client.get("/api/ui/portals").json()["portals"] == []

    client.post(
        "/logout",
        data={"csrf_token": csrf_token(client, "/dashboard")},
        follow_redirects=False,
    )
    login(client)
    assert step_up(client).status_code == 200
    grant = client.post(
        "/admin/portals/restricted-portal/grants",
        data={
            "username": "restricted-user",
            "expires_in_days": "1",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    assert grant.status_code in (302, 303)

    client.post(
        "/logout",
        data={"csrf_token": csrf_token(client, "/dashboard")},
        follow_redirects=False,
    )
    login(client, "restricted-user", "restricted-pass")
    portals = client.get("/api/ui/portals").json()["portals"]
    assert [portal["portal_name"] for portal in portals] == ["restricted-portal"]


def test_team_membership_inherits_expiring_portal_grant(client):
    from tests.conftest import csrf_token, login, step_up

    login(client)
    assert step_up(client).status_code == 200
    client.post(
        "/admin/portals",
        data={
            "portal_name": "team-portal",
            "display_name": "Team Portal",
            "secret": pyotp.random_base32(),
            "period": "30",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    client.post(
        "/admin/users",
        data={
            "username": "team-user",
            "password": "team-password",
            "role": "user",
            "csrf_token": csrf_token(client),
        },
        follow_redirects=False,
    )
    assert client.post(
        "/admin/teams",
        data={"name": "operations", "csrf_token": csrf_token(client)},
        follow_redirects=False,
    ).status_code in (302, 303)
    assert client.post(
        "/admin/teams/operations/members",
        data={"username": "team-user", "csrf_token": csrf_token(client)},
        follow_redirects=False,
    ).status_code in (302, 303)
    assert client.post(
        "/admin/teams/operations/grants/team-portal",
        data={"expires_in_days": "1", "csrf_token": csrf_token(client)},
        follow_redirects=False,
    ).status_code in (302, 303)

    client.post(
        "/logout",
        data={"csrf_token": csrf_token(client, "/dashboard")},
        follow_redirects=False,
    )
    login(client, "team-user", "team-password")
    portals = client.get("/api/ui/portals").json()["portals"]
    assert [portal["portal_name"] for portal in portals] == ["team-portal"]
