import os
import sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.sql_example_retrieval_service import sql_example_retrieval_service


async def main():
    count = sql_example_retrieval_service.count_examples()
    print(f"Examples in collection: {count}")

    query = "How many singers are there?"
    results = await sql_example_retrieval_service.retrieve_examples(query, limit=3)
    print(f"\nQuery: {query}\n")
    for i, r in enumerate(results, 1):
        print(f"{i}. similarity={r['similarity']:.3f} source={r['source']}")
        print(f"   Q: {r['question']}")
        print(f"   SQL: {r['sql'][:100]}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
