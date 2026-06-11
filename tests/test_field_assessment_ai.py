"""field_assessment_ai のテスト。

py -3 -m pytest tests/test_field_assessment_ai.py -q
"""

from fastapi.testclient import TestClient

from field_assessment_ai.app import app

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "precious_metal" in body["categories"]


def test_checklist_precious_metal():
    res = client.post("/api/assessment/checklist",
                      json={"category": "precious_metal", "visit": False})
    assert res.status_code == 200
    body = res.json()
    assert body["label"] == "貴金属"
    assert any("刻印" in c for c in body["checks"])
    assert any("本人確認" in d for d in body["documents"])


def test_checklist_visit_adds_cooling_off_caution():
    res = client.post("/api/assessment/checklist",
                      json={"category": "kimono", "visit": True})
    body = res.json()
    assert any("クーリング・オフ" in c for c in body["cautions"])


def test_checklist_unknown_category_falls_back_to_general():
    res = client.post("/api/assessment/checklist",
                      json={"category": "unknown", "visit": False})
    body = res.json()
    assert body["category"] == "general"
    assert body["label"] == "一般品"


def test_checklist_always_includes_disclaimer():
    for category in ["precious_metal", "kimono", "general"]:
        res = client.post("/api/assessment/checklist", json={"category": category})
        assert "保証" in res.json()["disclaimer"]
