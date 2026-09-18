def test_healthz_returns_200_and_expected_shape(client):
    response = client.get("/healthz")
    assert response.status_code == 200

    body = response.json()
    assert "model_version" in body
    assert "model_loaded" in body
    # Dengan mock_bert_load aktif (lihat conftest.py), model dianggap
    # sudah "dimuat" untuk keperluan test, tanpa beneran download.
    assert body["model_loaded"] is True
    assert body["status"] == "ok"
