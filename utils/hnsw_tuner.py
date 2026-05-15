import os
import json
import time
import argparse
from statistics import mean
from storage.vector.vector_store import VectorStore
from config_runtime import DATA_DIR

def load_queries(path: str):
    if not path:
        return [
            "滑坡的定义是什么",
            "A-17 参数是什么意思",
            "2023 年监测数据有哪些结论"
        ]
    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [str(x) for x in data if str(x).strip()]
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def percentile(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    idx = int(round((p / 100.0) * (len(values) - 1)))
    return float(values[max(0, min(idx, len(values) - 1))])

def benchmark(store: VectorStore, queries, repeats=3, top_k=4, search_mode="hybrid"):
    latencies = []
    hit_counts = []
    for _ in range(max(1, repeats)):
        for q in queries:
            started = time.perf_counter()
            results = store.search(q, top_k=top_k, search_mode=search_mode)
            cost_ms = (time.perf_counter() - started) * 1000
            latencies.append(cost_ms)
            hit_counts.append(len(results))
    stats = store.get_runtime_stats()
    return {
        "samples": len(latencies),
        "avg_ms": round(mean(latencies) if latencies else 0.0, 3),
        "p95_ms": round(percentile(latencies, 95), 3),
        "avg_hits": round(mean(hit_counts) if hit_counts else 0.0, 3),
        "cache_hit_rate": stats.get("cache_hit_rate", 0.0),
        "cache_size": stats.get("cache_size", 0)
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=str, default="")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--mode", type=str, default="hybrid")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--m", type=int, default=32)
    parser.add_argument("--ef-construction", type=int, default=200)
    parser.add_argument("--ef-search", type=int, default=80)
    parser.add_argument("--report", type=str, default=os.path.join(DATA_DIR, "hnsw_tuning_report.json"))
    args = parser.parse_args()

    queries = load_queries(args.queries)
    store = VectorStore(index_path="vector_db")

    before = benchmark(store, queries, repeats=args.repeats, top_k=args.top_k, search_mode=args.mode)
    report = {
        "queries": len(queries),
        "mode": args.mode,
        "before": before
    }

    if args.apply:
        store.rebuild_hnsw_index(
            m=args.m,
            ef_construction=args.ef_construction,
            ef_search=args.ef_search
        )
        after = benchmark(store, queries, repeats=args.repeats, top_k=args.top_k, search_mode=args.mode)
        report["applied"] = {
            "m": args.m,
            "ef_construction": args.ef_construction,
            "ef_search": args.ef_search
        }
        report["after"] = after

    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
