from pathlib import Path

from autods.sessions import SessionStorage


def test_upsert_auth_user_keeps_workos_identity_when_email_belongs_to_other_user(
    tmp_path: Path,
) -> None:
    storage = SessionStorage(root=tmp_path / "sessions")
    first = storage.upsert_auth_user(
        workos_user_id="wos-user-a",
        email="first@example.com",
        display_name="First User",
    )
    second = storage.upsert_auth_user(
        workos_user_id="wos-user-b",
        email="second@example.com",
        display_name="Second User",
    )

    updated = storage.upsert_auth_user(
        workos_user_id="wos-user-b",
        email="first@example.com",
        display_name="Second User Updated",
    )

    assert updated.id == second.id
    assert updated.workos_user_id == second.workos_user_id
    assert updated.email == second.email
    assert updated.display_name == "Second User Updated"

    users = {user.id: user for user in storage.list_auth_users()}
    assert users[first.id].email == first.email
    assert users[second.id].email == second.email
