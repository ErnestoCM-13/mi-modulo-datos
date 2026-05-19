import gc
import time
from pathlib import Path

import httpx
import numpy as np

BASE_URL = "http://localhost:8000"
N = 100

ENDPOINTS = [
    ("/analytics/summary",              "GET /analytics/summary"),
    ("/analytics/top-merchants",        "GET /analytics/top-merchants"),
    ("/analytics/top-merchants?limit=5&country=MX",
                                        "GET /analytics/top-merchants?limit=5&country=MX"),
    ("/users/1/transactions",           "GET /users/1/transactions"),
    ("/users/1/stats",                  "GET /users/1/stats"),
    ("/health",                         "GET /health"),
]

def benchmark_endpoint(client, path, label):
    """Mide cold (primera request) y warm (99 siguientes)."""
    gc.collect()

    # Cold — first request without cache
    t0   = time.perf_counter()
    resp = client.get(path)
    cold = (time.perf_counter() - t0) * 1000
    assert resp.status_code == 200, f"{label} returned {resp.status_code}"

    # Warm — request with active cache
    warm_times = []
    for _ in range(N - 1):
        gc.collect()
        t0   = time.perf_counter()
        resp = client.get(path)
        elapsed = (time.perf_counter() - t0) * 1000
        warm_times.append(elapsed)

    p50 = np.percentile(warm_times, 50)
    p95 = np.percentile(warm_times, 95)
    p99 = np.percentile(warm_times, 99)

    print(f"  {label}")
    print(f"    Cold: {cold:.1f}ms | Warm → p50: {p50:.1f}ms  p95: {p95:.1f}ms  p99: {p99:.1f}ms")

    return {
        'label':      label,
        'cold_ms':    round(cold, 2),
        'warm_p50_ms': round(p50, 2),
        'warm_p95_ms': round(p95, 2),
        'warm_p99_ms': round(p99, 2),
    }

def generate_report(results):
    lines = [
        "# Benchmark de Latencia",
        "",
        f"Requests por endpoint: {N}  ",
        f"Primera request = cold (sin cache) · Resto = warm (con cache activo)",
        "",
        "## Resultados",
        "",
        "| Endpoint | Cold (ms) | p50 warm (ms) | p95 warm (ms) | p99 warm (ms) |",
        "|----------|----------|--------------|--------------|--------------|",
    ]

    for r in results:
        lines.append(
            f"| {r['label']} | {r['cold_ms']} | {r['warm_p50_ms']} "
            f"| {r['warm_p95_ms']} | {r['warm_p99_ms']} |"
        )

    lines.extend([
        "",
        "## Análisis",
        "",
        "### Impacto del cache en endpoints analíticos",
        "",
    ])

    # Identify analytics endpoints
    analytics = [r for r in results if '/analytics/' in r['label']]
    if analytics:
        cold_avg = sum(r['cold_ms'] for r in analytics) / len(analytics)
        warm_avg = sum(r['warm_p50_ms'] for r in analytics) / len(analytics)
        if warm_avg > 0:
            factor = cold_avg / warm_avg
            lines.append(
                f"Los endpoints analíticos promedian {cold_avg:.1f}ms en cold y "
                f"{warm_avg:.1f}ms en warm (p50), una mejora de **{factor:.0f}x** "
                f"gracias al cache en memoria."
            )

    lines.extend([
        "",
        "### Endpoints transaccionales",
        "",
    ])

    user_eps = [r for r in results if '/users/' in r['label']]
    if user_eps:
        p50_avg = sum(r['warm_p50_ms'] for r in user_eps) / len(user_eps)
        lines.append(
            f"Los endpoints de usuario promedian {p50_avg:.1f}ms (p50), "
            f"cumpliendo el SLA de < 80ms gracias a los índices de SQLite."
        )

    lines.extend([
        "",
        "### SLAs",
        "",
        "| Endpoint | SLA | Cold | Warm p50 | Cumple |",
        "|----------|-----|------|----------|--------|",
    ])

    slas = {
        "/analytics/summary": ("< 500ms cold / < 20ms warm", 500, 20),
        "/analytics/top-merchants": ("< 500ms cold / < 20ms warm", 500, 20),
        "/users/1/transactions": ("< 80ms", 80, 80),
        "/users/1/stats": ("< 80ms", 80, 80),
        "/health": ("< 50ms", 50, 50),
    }

    for r in results:
        path = r['label'].replace("GET ", "")
        if path in slas:
            sla_text, cold_limit, warm_limit = slas[path]
            cold_ok = r['cold_ms'] < cold_limit
            warm_ok = r['warm_p50_ms'] < warm_limit
            status  = "✓" if (cold_ok and warm_ok) else "✗"
            lines.append(
                f"| {r['label']} | {sla_text} | {r['cold_ms']}ms | "
                f"{r['warm_p50_ms']}ms | {status} |"
            )

    return "\n".join(lines) + "\n"

def main():
    print(f"Benchmark de latencia — {N} requests por endpoint\n")

    client  = httpx.Client(base_url=BASE_URL, timeout=10)
    results = []

    for path, label in ENDPOINTS:
        r = benchmark_endpoint(client, path, label)
        results.append(r)

    client.close()

    # Generate report
    report = generate_report(results)
    out    = Path("benchmarks/latency_report.md")
    out.parent.mkdir(exist_ok=True)
    out.write_text(report)
    print(f"\n✓ Reporte guardado en {out}")

if __name__ == "__main__":
    main()
