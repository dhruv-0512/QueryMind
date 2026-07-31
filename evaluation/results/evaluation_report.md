# QueryMind Engineering Evaluation Report

> [!NOTE]
> Evaluated on **unseen natural language query paraphrases** from custom benchmark dataset (`evaluation/database/db_engine.py`).

---

## 1. Executive Performance Metrics

| Metric Category | Metric Name | Score | Target Standard | Status |
| :--- | :--- | :--- | :--- | :--- |
| **SQL Generation** | **Execution Accuracy** | `93.88%` | `> 85.0%` | **PASSED** |
| **SQL Generation** | **Semantic Answer Accuracy** | `93.88%` | `> 80.0%` | **PASSED** |
| **Retrieval** | **Top-1 Recall** | `100.0%` | `> 90.0%` | **PASSED** |
| **Retrieval** | **Top-5 Recall** | `100.0%` | `> 95.0%` | **PASSED** |
| **Retrieval** | **Mean Reciprocal Rank (MRR)** | `1.0` | `> 0.90` | **PASSED** |
| **Latency** | **Average End-to-End Latency** | `1.5079 s` | `< 2.0 s` | **OPTIMAL** |
| **Latency** | **P95 Latency** | `1.8698 s` | `< 2.5 s` | **OPTIMAL** |
| **Security** | **Prohibited SQL Injection Block Rate** | `4/4 (100%)` | `100%` | **SECURE** |

---

## 2. Latency Breakdown per Stage

- **Retriever Latency**: `0.0196s` (Avg) / `0.0239s` (P95)
- **Embedding Latency**: `0.0134s` (Avg) / `0.017s` (P95)
- **LLM Generation Latency**: `1.4735s` (Avg) / `1.8375s` (P95)
- **SQL Execution Latency**: `0.0014s` (Avg) / `0.0027s` (P95)
- **Total System Latency**: `1.5079s` (Avg) / `1.8698s` (P95)

---

*Report generated automatically inside evaluation/results/.*