import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

# --- 1. Health ---

def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "uptime_s" in data
    assert "cache_hit_rate" in data
    assert data["connections"]["sqlite"] is True
    assert data["connections"]["duckdb"] is True

# --- 2. Analytics summary ───

def test_analytics_summary_structure(client):
    resp = client.get("/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_count" in data
    assert "total_amount" in data
    assert "avg_amount" in data
    assert isinstance(data["by_country"], list)
    assert isinstance(data["by_category"], list)
    assert data["total_count"] > 0

# --- 3. Top merchants (default) ───

def test_top_merchants_default(client):
    resp = client.get("/analytics/top-merchants")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 10
    assert "merchant_id" in data[0]
    assert "total_volume" in data[0]

# --- 4. Top merchants (with country filter) ───

def test_top_merchants_with_country(client):
    resp = client.get("/analytics/top-merchants?limit=5&country=MX")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) <= 5

# --- 5. User transactions (happy path) ───

def test_user_transactions_happy_path(client):
    resp = client.get("/users/1/transactions")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "transaction_id" in data[0]

# --- 6. Non-existent user → 404 ───

def test_user_not_found_404(client):
    resp = client.get("/users/99999999/transactions")
    assert resp.status_code == 404

# --- 7. Pagination out of range → empty list ───

def test_pagination_out_of_range(client):
    resp = client.get("/users/1/transactions?page=9999&page_size=20")
    assert resp.status_code == 200
    data = resp.json()
    assert data == []

# --- 8. User stats (happy path) ───

def test_user_stats_happy_path(client):
    resp = client.get("/users/1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == 1
    assert "total_amount" in data
    assert "transaction_count" in data
    assert "top_category" in data
    assert "country_code" in data

# --- 9. Valid batch ───

def test_batch_valid(client):
    txns = [
        {
            "transaction_id": str(uuid.uuid4()),
            "timestamp":      "2026-05-01 12:00:00",
            "user_id":        1,
            "merchant_id":    1,
            "amount":         100.50,
            "category":       "Food",
            "country_code":   "MX",
            "status":         "completed",
        }
    ]
    resp = client.post("/transactions/batch", json=txns)
    assert resp.status_code == 200
    data = resp.json()
    assert data["received"] == 1
    assert data["inserted"] == 1

# --- 10. Batch with invalid schema → 422 ───

def test_batch_invalid_schema_422(client):
    bad_txns = [
        {
            "transaction_id": "abc",
            "amount": "not_a_number",
        }
    ]
    resp = client.post("/transactions/batch", json=bad_txns)
    assert resp.status_code == 422

# --- 11. Latency SLA — analytics summary in Warm ───

def test_analytics_summary_sla(client):
    # First call to warm the cache
    client.get("/analytics/summary")

    # Second call (warm)
    start = time.perf_counter()
    resp  = client.get("/analytics/summary")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert resp.status_code == 200
    assert elapsed_ms < 20, f"SLA violated: {elapsed_ms:.1f}ms > 20ms"
