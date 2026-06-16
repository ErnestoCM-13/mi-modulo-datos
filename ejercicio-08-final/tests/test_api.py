import io
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# --- Health ---

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "uptime_s" in data
    assert "cache_hit_rate" in data
    assert "transaction_count" in data
    assert data["connections"]["sqlite"] is True
    assert data["connections"]["duckdb"] is True


# --- Analytics ---

def test_analytics_summary(client):
    resp = client.get("/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] > 0
    assert "by_country" in data
    assert "by_category" in data


def test_top_merchants_default(client):
    resp = client.get("/analytics/top-merchants")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 10


def test_top_merchants_with_country(client):
    resp = client.get("/analytics/top-merchants?limit=5&country=MX")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) <= 5


# --- User transactions ---

def test_user_transactions(client):
    resp = client.get("/users/1/transactions")
    assert resp.status_code in [200, 404]


def test_user_transactions_with_date_filter(client):
    resp = client.get("/users/1/transactions?date_from=2025-01-01&date_to=2026-12-31")
    assert resp.status_code in [200, 404]


def test_user_not_found(client):
    resp = client.get("/users/99999999/transactions")
    assert resp.status_code == 404


def test_user_stats(client):
    resp = client.get("/users/1/stats")
    assert resp.status_code in [200, 404]
    if resp.status_code == 200:
        data = resp.json()
        assert "total_amount" in data
        assert "top_category" in data


# --- Anomaly detection ---

def test_anomalies_default(client):
    resp = client.get("/anomalies/failed-transactions")
    assert resp.status_code == 200
    data = resp.json()
    assert "threshold" in data
    assert "days" in data
    assert "total_users" in data
    assert isinstance(data["users"], list)


def test_anomalies_custom_threshold(client):
    resp = client.get("/anomalies/failed-transactions?threshold=2&days=60")
    assert resp.status_code == 200
    data = resp.json()
    assert data["threshold"] == 2
    assert data["days"] == 60


# --- CSV ingestion ---

def test_csv_ingest_valid(client):
    tid = str(uuid.uuid4())
    csv_content = (
        "transaction_id,timestamp,user_id,merchant_id,amount,category,country_code,status\n"
        f"{tid},2026-05-01 12:00:00,1,1,100.50,Food,MX,completed\n"
    )
    resp = client.post(
        "/ingest/csv",
        files={"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rows_extracted"] == 1
    assert data["rows_inserted"] == 1


def test_csv_ingest_with_errors(client):
    csv_content = (
        "transaction_id,timestamp,user_id,merchant_id,amount,category,country_code,status\n"
        "not-a-uuid,2026-05-01 12:00:00,1,1,100.50,Food,MX,completed\n"
        f"{uuid.uuid4()},2026-05-01 12:00:00,1,1,-50.00,Food,MX,completed\n"
    )
    resp = client.post(
        "/ingest/csv",
        files={"file": ("bad.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rows_rejected"] >= 2


def test_csv_ingest_non_csv_rejected(client):
    resp = client.post(
        "/ingest/csv",
        files={"file": ("data.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 422


# --- SLA ---

def test_analytics_summary_sla(client):
    client.get("/analytics/summary")  # warm cache
    start = time.perf_counter()
    resp  = client.get("/analytics/summary")
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.status_code == 200
    assert elapsed_ms < 20, f"SLA violated: {elapsed_ms:.1f}ms > 20ms"
