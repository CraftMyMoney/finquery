from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    # db may be down in CI; the key contract is the endpoint answers
    assert isinstance(body["db"], bool)


def test_ask_stub_contract():
    res = client.post("/ask", json={"question": "What is the 50/30/20 rule?", "approach": "rag"})
    assert res.status_code == 200
    body = res.json()
    assert set(body) >= {"answer", "approach", "refused", "citations"}
    assert body["approach"] == "rag"
    assert body["refused"] is False


def test_ask_rejects_bad_approach():
    res = client.post("/ask", json={"question": "hi", "approach": "graphrag"})
    assert res.status_code == 422


def test_ui_served_at_root():
    res = client.get("/")
    assert res.status_code == 200
    assert "FinQuery" in res.text
