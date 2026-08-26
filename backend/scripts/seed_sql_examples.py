"""
Seed sql_examples_collection in ChromaDB from local archive.zip (Spider)
and archive (1).zip (WikiSQL). Curates ~2500 diverse question-SQL pairs
with a heavily expanded JOIN quota drawn entirely from Spider/WikiSQL.
"""
import os
import sys
import json
import hashlib
import re
import zipfile
import asyncio
import logging
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.sql_example_retrieval_service import sql_example_retrieval_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("seed_sql_examples")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPIDER_ZIP = os.path.join(PROJECT_ROOT, "archive.zip")
WIKISQL_ZIP = os.path.join(PROJECT_ROOT, "archive (1).zip")
DATASETS_DIR = os.path.join(PROJECT_ROOT, "datasets")

# Increased target to absorb more JOIN/multi-table coverage from Spider
TARGET_TOTAL = 2500
SAMPLES_PER_PATTERN = {
    "subquery":        100,
    "having":          100,
    "union":           100,
    "set_operation":    80,
    "join":            700,   # heavily expanded — Spider is rich in JOINs
    "group_by":        300,
    "aggregation":     300,
    "select_where":    400,
    "select":          200,
}
COMPLEXITY_RATIOS = {"simple": 0.30, "medium": 0.45, "hard": 0.25}

SPIDER_JSON_PATHS = [
    "spider/train_spider.json",
    "spider/dev.json",
    "spider/train_others.json",
]
WIKISQL_JSON_PATHS = [
    "wikisql_train.json",
    "wikisql_validation.json",
    "wikisql_test.json",
]


def stable_id(source: str, question: str, sql: str) -> str:
    content = f"{source}|{question.strip().lower()}|{sql.strip().lower()}"
    return f"ex:{source}:{hashlib.sha256(content.encode()).hexdigest()[:16]}"


def _count_joins(sql: str) -> int:
    return len(re.findall(r"\bJOIN\b", sql, re.IGNORECASE))


def _join_type(sql: str) -> str:
    """Return the most complex join type present in the SQL."""
    s = sql.upper()
    if "FULL" in s and "OUTER" in s:
        return "FULL OUTER JOIN"
    if "CROSS" in s and "JOIN" in s:
        return "CROSS JOIN"
    if "RIGHT" in s and "JOIN" in s:
        return "RIGHT JOIN"
    if "LEFT" in s and "JOIN" in s:
        return "LEFT JOIN"
    if "INNER" in s and "JOIN" in s:
        return "INNER JOIN"
    if "JOIN" in s:
        return "JOIN"
    return ""


def _has_self_join(sql: str) -> bool:
    """Heuristic: self-join uses the same table twice with different aliases."""
    tables = re.findall(r'\b(?:FROM|JOIN)\s+["`]?(\w+)["`]?', sql, re.IGNORECASE)
    return len(tables) != len(set(t.lower() for t in tables))


def classify_pattern(sql: str) -> str:
    s = sql.lower().strip()
    # CTE -> subquery bucket
    if s.startswith("with ") and "select" in s:
        return "subquery"
    if re.search(r"\(\s*select\b", s):
        return "subquery"
    if "having" in s:
        return "having"
    if "union" in s:
        return "union"
    if "intersect" in s or "except" in s:
        return "set_operation"
    if "join" in s:
        return "join"
    if "group by" in s:
        return "group_by"
    if re.search(r"\b(count|avg|sum|max|min)\s*\(", s):
        return "aggregation"
    if "where" in s:
        return "select_where"
    return "select"


def classify_complexity(sql: str) -> str:
    s = sql.lower()
    join_count = _count_joins(sql)
    if join_count >= 3 or s.count("select") >= 2:
        return "hard"
    if join_count >= 1 or "group by" in s or "having" in s or "union" in s:
        return "medium"
    return "simple"


def classify_difficulty(sql: str, complexity: str) -> str:
    """Extended difficulty tag for multi-table evaluation."""
    join_count = _count_joins(sql)
    if join_count >= 3:
        return "advanced_multi_table"
    if join_count == 2:
        return "multi_table"
    if join_count == 1:
        return "multi_table"
    if complexity == "hard":
        return "hard"
    if complexity == "medium":
        return "medium"
    return "easy"


def _text_hash(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode()).hexdigest()


def _example(question: str, sql: str, source: str) -> dict:
    pattern = classify_pattern(sql)
    complexity = classify_complexity(sql)
    join_count = _count_joins(sql)
    return {
        "id": stable_id(source, question, sql),
        "question": question.strip(),
        "sql": sql.strip(),
        "pattern_type": pattern,
        "complexity": complexity,
        "source": source,
        # Extended metadata for multi-table retrieval quality scoring
        "difficulty": classify_difficulty(sql, complexity),
        "join_count": join_count,
        "join_type": _join_type(sql),
        "has_aggregation": bool(re.search(r"\b(count|avg|sum|max|min)\s*\(", sql, re.IGNORECASE)),
        "has_subquery": bool(re.search(r"\(\s*select\b", sql, re.IGNORECASE)),
        "has_cte": sql.strip().lower().startswith("with "),
        "has_self_join": _has_self_join(sql) if join_count > 0 else False,
    }


def load_spider_from_zip() -> list:
    if not os.path.exists(SPIDER_ZIP):
        logger.warning(f"Spider archive not found: {SPIDER_ZIP}")
        return []

    examples = []
    with zipfile.ZipFile(SPIDER_ZIP) as zf:
        for path in SPIDER_JSON_PATHS:
            if path not in zf.namelist():
                logger.warning(f"Missing in archive: {path}")
                continue
            with zf.open(path) as f:
                data = json.load(f)
            for item in data:
                q, sql = item.get("question"), item.get("query")
                if q and sql:
                    examples.append(_example(q, sql, "spider"))
            logger.info(f"Loaded {path}: {len(data)} rows")

    logger.info(f"Spider total: {len(examples)}")
    return examples


def load_spider_from_disk() -> list:
    path = os.path.join(DATASETS_DIR, "spider", "dev.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [_example(i["question"], i["query"], "spider") for i in data if i.get("question") and i.get("query")]


def load_wikisql_from_zip() -> list:
    if not os.path.exists(WIKISQL_ZIP):
        logger.warning(f"WikiSQL archive not found: {WIKISQL_ZIP}")
        return []

    examples = []
    with zipfile.ZipFile(WIKISQL_ZIP) as zf:
        for path in WIKISQL_JSON_PATHS:
            if path not in zf.namelist():
                continue
            with zf.open(path) as f:
                data = json.load(f)
            for item in data:
                q, sql = item.get("question"), item.get("answer")
                if q and sql:
                    examples.append(_example(q, sql, "wikisql"))
            logger.info(f"Loaded {path}: {len(data)} rows")

    logger.info(f"WikiSQL total: {len(examples)}")
    return examples


def load_wikisql_from_disk() -> list:
    examples = []
    for split in ["train", "test", "validation"]:
        path = os.path.join(DATASETS_DIR, f"wikisql_{split}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            q, sql = item.get("question"), item.get("answer")
            if q and sql:
                examples.append(_example(q, sql, "wikisql"))
    return examples


def curate(examples: list, target_total: int = TARGET_TOTAL) -> list:
    """
    Curate examples by pattern/complexity quotas with deduplication.

    JOIN examples are sampled with a sub-quota breakdown:
      - join_count == 1 : up to 350 (basic 2-table)
      - join_count == 2 : up to 200 (3-table)
      - join_count >= 3 : up to 150 (4-table / complex)
    This ensures diverse multi-table coverage within the JOIN bucket.
    """
    by_pattern = defaultdict(list)
    for ex in examples:
        by_pattern[ex["pattern_type"]].append(ex)

    curated = []
    seen_hashes = set()

    for pattern, pool in by_pattern.items():
        cap = SAMPLES_PER_PATTERN.get(pattern, 50)

        if pattern == "join":
            # Sub-bucket JOIN examples by join depth
            by_depth = defaultdict(list)
            for ex in pool:
                jc = ex.get("join_count", 0)
                if jc <= 1:
                    by_depth["single"].append(ex)
                elif jc == 2:
                    by_depth["double"].append(ex)
                else:
                    by_depth["multi"].append(ex)

            sub_caps = {"single": 350, "double": 200, "multi": 150}
            join_picked = 0

            for depth_key, sub_cap in sub_caps.items():
                sub_pool = by_depth[depth_key]
                by_complexity = defaultdict(list)
                for ex in sub_pool:
                    by_complexity[ex["complexity"]].append(ex)

                for complexity in COMPLEXITY_RATIOS:
                    bucket = by_complexity.get(complexity, [])
                    bucket.sort(key=lambda x: len(x["question"]), reverse=True)
                    for ex in bucket:
                        if join_picked >= cap:
                            break
                        key = _text_hash(ex["sql"][:80] + ex["question"][:80])
                        if key in seen_hashes:
                            continue
                        seen_hashes.add(key)
                        curated.append(ex)
                        join_picked += 1
                    if join_picked >= cap:
                        break

                # Fill remainder without complexity constraint
                for ex in sub_pool:
                    if join_picked >= cap:
                        break
                    key = _text_hash(ex["sql"][:80] + ex["question"][:80])
                    if key in seen_hashes:
                        continue
                    seen_hashes.add(key)
                    curated.append(ex)
                    join_picked += 1
                if join_picked >= cap:
                    break

            logger.info(
                f"JOIN bucket: {join_picked} selected "
                f"(single={len(by_depth['single'])}, "
                f"double={len(by_depth['double'])}, "
                f"multi={len(by_depth['multi'])} available)"
            )
            continue  # already handled

        # All other patterns: complexity-stratified sampling
        by_complexity = defaultdict(list)
        for ex in pool:
            by_complexity[ex["complexity"]].append(ex)

        picked = 0
        for complexity in COMPLEXITY_RATIOS:
            bucket = by_complexity.get(complexity, [])
            bucket.sort(key=lambda x: len(x["question"]), reverse=True)
            for ex in bucket:
                if picked >= cap:
                    break
                key = _text_hash(ex["sql"][:80] + ex["question"][:80])
                if key in seen_hashes:
                    continue
                seen_hashes.add(key)
                curated.append(ex)
                picked += 1

        for ex in pool:
            if picked >= cap:
                break
            key = _text_hash(ex["sql"][:80] + ex["question"][:80])
            if key in seen_hashes:
                continue
            seen_hashes.add(key)
            curated.append(ex)
            picked += 1

    if len(curated) > target_total:
        spider_first = [e for e in curated if e["source"] == "spider"]
        wikisql_rest = [e for e in curated if e["source"] == "wikisql"]
        ratio = len(spider_first) / max(len(curated), 1)
        spider_cap = int(target_total * ratio)
        curated = spider_first[:spider_cap] + wikisql_rest[: target_total - spider_cap]

    # Log coverage breakdown
    join_examples = [e for e in curated if e["pattern_type"] == "join"]
    multi_table = [e for e in join_examples if e.get("join_count", 0) >= 2]
    logger.info(
        f"Curated {len(curated)} from {len(examples)} raw (target={target_total})\n"
        f"  JOIN examples     : {len(join_examples)}\n"
        f"  Multi-table (2+J) : {len(multi_table)}\n"
        f"  Difficulty breakdown: "
        + str({d: sum(1 for e in curated if e.get('difficulty') == d)
               for d in ['easy', 'medium', 'hard', 'multi_table', 'advanced_multi_table']})
    )
    return curated


async def seed(reset: bool = False) -> None:
    try:
        sql_example_retrieval_service._ensure_connected()
    except Exception as e:
        logger.error(f"ChromaDB connection failed: {e}")
        sys.exit(1)

    if reset:
        sql_example_retrieval_service.reset_collection()
        logger.info("Cleared sql_examples_collection")

    raw = load_spider_from_zip() + load_wikisql_from_zip()
    if not raw:
        raw = load_spider_from_disk() + load_wikisql_from_disk()
    if not raw:
        from app.resources.canonical_sql_examples import CANONICAL_SQL_EXAMPLES
        logger.info("Using curated canonical Spider and WikiSQL benchmark dataset.")
        raw = [_example(e["question"], e["sql"], e["source"]) for e in CANONICAL_SQL_EXAMPLES]

    logger.info(
        f"Raw dataset: {len(raw)} total "
        f"({sum(1 for e in raw if e['pattern_type'] == 'join')} JOINs, "
        f"{sum(1 for e in raw if e.get('join_count', 0) >= 2)} multi-table)"
    )

    curated = curate(raw)
    logger.info(f"Seeding {len(curated)} curated examples (upsert, idempotent)...")

    chunk_size = 50
    for i in range(0, len(curated), chunk_size):
        chunk = curated[i : i + chunk_size]
        await sql_example_retrieval_service.upsert_examples(chunk)
        logger.info(f"  {min(i + chunk_size, len(curated))}/{len(curated)}")

    count = sql_example_retrieval_service.count_examples()
    logger.info(f"Done. Total in sql_examples_collection: {count}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed SQL examples into ChromaDB")
    parser.add_argument("--reset", action="store_true", help="Clear collection before seeding")
    args = parser.parse_args()
    asyncio.run(seed(reset=args.reset))
