from __future__ import annotations

import base64
from pathlib import Path

from fastapi.testclient import TestClient

from field_assessment_ai.app import create_app
from field_assessment_ai.config import AppSettings


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAA=="
)


def make_client(tmp_path: Path) -> tuple[TestClient, AppSettings]:
    settings = AppSettings(runtime_root=tmp_path / "runtime")
    app = create_app(settings)
    return TestClient(app), settings


def test_core_flow(tmp_path: Path) -> None:
    client, settings = make_client(tmp_path)
    with client:
        health = client.get("/api/v0/health")
        assert health.status_code == 200

        job = client.post(
            "/api/v0/jobs",
            json={
                "title": "案件A",
                "customer_name": "顧客",
                "address": "住所",
            },
        ).json()
        item = client.post(
            "/api/v0/items",
            json={
                "job_id": job["id"],
                "name": "Nintendo Switch 本体",
                "category": "ゲーム",
                "brand": "Nintendo",
                "condition_note": "箱あり",
            },
        ).json()

        upload = client.post(
            f"/api/v0/items/{item['id']}/images",
            files={"file": ("sample.png", PNG_BYTES, "image/png")},
        ).json()
        assert upload["public_url"].startswith("/uploads/items/")

        item_detail = client.get(f"/api/v0/items/{item['id']}").json()
        assert item_detail["analysis"]["source"] == "mock-vision"
        assert len(item_detail["images"]) == 1

        links = client.post("/api/v0/search-links", json={"item_id": item["id"]}).json()
        assert links["search_links"]["mercari"].startswith("https://jp.mercari.com/search?keyword=")
        assert len(links["search_links"]) == 8

        memo = client.put(f"/api/v0/items/{item['id']}/market-memo", json={}).json()
        assert memo["search_keyword"]

        estimate = client.post(f"/api/v0/calculations/items/{item['id']}", json={}).json()
        assert estimate["estimate"]["rank_candidate"] in {"A", "B", "C", "D", "E", "F"}

        report = client.post("/api/v0/reports/draft", json={"job_id": job["id"], "format": "json"}).json()
        assert report["report"]["format"] == "json"
        assert report["content_json"]["summary"]["item_count"] >= 1

        latest = client.get(f"/api/v0/estimates/items/{item['id']}/latest").json()
        assert latest["estimate"]["id"] == estimate["estimate"]["id"]

    # the app should release the SQLite file on shutdown
    assert settings.database_path.exists()


def test_delete_job_cascades_items_and_images(tmp_path: Path) -> None:
    client, settings = make_client(tmp_path)
    with client:
        job = client.post("/api/v0/jobs", json={"title": "案件B"}).json()
        item = client.post("/api/v0/items", json={"job_id": job["id"], "name": "壊れたテレビ", "category": "テレビ"}).json()
        upload = client.post(
            f"/api/v0/items/{item['id']}/images",
            files={"file": ("sample.png", PNG_BYTES, "image/png")},
        ).json()
        image_id = upload["id"]
        image_path = settings.upload_dir / upload["relative_path"]

        delete_image = client.delete(f"/api/v0/images/{image_id}")
        assert delete_image.status_code == 200
        assert not image_path.exists()

        delete_job = client.delete(f"/api/v0/jobs/{job['id']}")
        assert delete_job.status_code == 200
        assert client.get(f"/api/v0/jobs/{job['id']}").status_code == 404
        assert client.get(f"/api/v0/items/{item['id']}").status_code == 404
