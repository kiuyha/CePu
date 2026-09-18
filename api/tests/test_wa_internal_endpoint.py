"""
Test untuk POST /internal/wa/inbound: validasi X-Internal-Token, dan
integrasi dasar dengan wa_bot.
"""
from api.core.config import get_settings

SETTINGS = get_settings()


def test_wa_inbound_without_token_returns_401(client):
    response = client.post(
        "/internal/wa/inbound",
        json={"phone_hash": "abc123", "msg": {"type": "text", "body": "halo"}},
    )
    assert response.status_code == 401


def test_wa_inbound_with_wrong_token_returns_401(client):
    response = client.post(
        "/internal/wa/inbound",
        json={"phone_hash": "abc123", "msg": {"type": "text", "body": "halo"}},
        headers={"X-Internal-Token": "token-salah"},
    )
    assert response.status_code == 401


def test_wa_inbound_with_correct_token_returns_200(client):
    response = client.post(
        "/internal/wa/inbound",
        json={"phone_hash": "abc123", "msg": {"type": "text", "body": "halo"}},
        headers={"X-Internal-Token": SETTINGS.internal_token},
    )
    assert response.status_code == 200
    assert "reply" in response.json()


def test_wa_inbound_returns_main_menu_for_unrecognized_text(client):
    response = client.post(
        "/internal/wa/inbound",
        json={"phone_hash": "user-menu-test", "msg": {"type": "text", "body": "xyz123"}},
        headers={"X-Internal-Token": SETTINGS.internal_token},
    )
    reply = response.json()["reply"]
    assert "Pilih menu" in reply
