import os
import sys
import asyncio
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.sql_example_retrieval_service import SqlExampleRetrievalService
from app.services.sql_service import SqlService


class TestSqlExampleRetrieval(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.retrieval_service = SqlExampleRetrievalService()
        self.mock_client = MagicMock()
        self.mock_collection = MagicMock()
        self.mock_client.get_or_create_collection.return_value = self.mock_collection
        self.retrieval_service.client = self.mock_client
        self.retrieval_service.collection = self.mock_collection

    @patch("app.services.sql_example_retrieval_service.get_embeddings_batch")
    async def test_upsert_examples(self, mock_get_embeddings):
        mock_get_embeddings.return_value = [[0.1] * 768, [0.2] * 768]

        examples = [
            {
                "id": "ex:spider:abc123",
                "question": "How many employees are there?",
                "sql": "SELECT count(*) FROM employees",
                "pattern_type": "aggregation",
                "complexity": "simple",
                "source": "spider",
            },
            {
                "question": "What is the max salary?",
                "sql": "SELECT max(salary) FROM employees",
                "pattern_type": "aggregation",
                "complexity": "simple",
                "source": "wikisql",
            },
        ]

        await self.retrieval_service.upsert_examples(examples)

        self.mock_collection.upsert.assert_called_once()
        kwargs = self.mock_collection.upsert.call_args.kwargs
        self.assertEqual(len(kwargs["ids"]), 2)
        self.assertEqual(kwargs["ids"][0], "ex:spider:abc123")
        self.assertTrue(kwargs["ids"][1].startswith("ex:wikisql:"))

    @patch("app.services.sql_example_retrieval_service.get_query_embedding")
    async def test_retrieve_examples_with_similarity(self, mock_get_embedding):
        mock_get_embedding.return_value = [0.1] * 768

        self.mock_collection.query.return_value = {
            "metadatas": [[
                {
                    "question": "How many employees are there?",
                    "sql": "SELECT count(*) FROM employees",
                    "pattern_type": "aggregation",
                    "complexity": "simple",
                    "source": "spider",
                }
            ]],
            "distances": [[0.1]],
        }

        results = await self.retrieval_service.retrieve_examples("Count employees", limit=1)

        self.mock_collection.query.assert_called_once()
        self.assertEqual(len(results), 1)
        self.assertIn("similarity", results[0])
        self.assertGreater(results[0]["similarity"], 0.9)


class TestSqlRagAdaptation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sql_service = SqlService()

    def test_adapt_sql_from_example(self):
        schema = 'CREATE TABLE customers (\n  id INTEGER,\n  name TEXT,\n  city TEXT\n);'
        example_sql = "SELECT name FROM users WHERE city = 'New York'"
        adapted = self.sql_service._adapt_sql_from_example(example_sql, schema)
        self.assertIn("customers", adapted)
        self.assertIn("name", adapted)
        self.assertIn("city", adapted)

    def test_rag_direct_on_high_similarity(self):
        schema = 'CREATE TABLE customers (\n  id INTEGER,\n  name TEXT,\n  city TEXT\n);'
        examples = [{
            "question": "Show names from Boston",
            "sql": "SELECT name FROM users WHERE city = 'Boston'",
            "similarity": 0.85,
            "source": "spider",
        }]
        result = self.sql_service._try_rag_direct(schema, "names in Boston", examples)
        self.assertIsNotNone(result)
        self.assertEqual(result["rag_mode"], "direct")
        self.assertIn("customers", result["sql"])

    def test_rag_direct_skips_low_similarity(self):
        schema = "CREATE TABLE t (id INT);"
        examples = [{"question": "q", "sql": "SELECT 1", "similarity": 0.5}]
        self.assertIsNone(self.sql_service._try_rag_direct(schema, "q", examples))

    @patch("app.services.sql_service.is_api_key_configured")
    @patch("app.services.sql_service.genai.GenerativeModel")
    async def test_generate_sql_rag_prompt(self, mock_model_class, mock_key):
        mock_key.return_value = True
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model
        self.sql_service.model = mock_model

        captured = {}

        async def mock_generate(*args, **kwargs):
            captured["prompt"] = args[0]
            resp = MagicMock()
            resp.text = '{"sql": "SELECT name FROM customer WHERE city = \'New York\';", "explanation": "ok", "confidence": 0.9}'
            return resp

        mock_model.generate_content_async = mock_generate

        schema = "CREATE TABLE customer (id INT, name TEXT, city TEXT);"
        examples = [{
            "question": "Show users from Boston",
            "sql": "SELECT username FROM users WHERE location = 'Boston';",
            "similarity": 0.6,
            "source": "spider",
        }]

        result = await self.sql_service.generate_sql(schema, "names in New York", examples)
        self.assertEqual(result["rag_mode"], "llm_adapt")
        self.assertIn("PRIMARY PATTERN", captured["prompt"])
        self.assertIn("SIMILAR SQL EXAMPLES", captured["prompt"])


if __name__ == "__main__":
    unittest.main()
