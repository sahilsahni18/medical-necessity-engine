"""Run the ingestion pipeline once: python -m scripts.ingest"""

from app.ingestion import run_ingestion

if __name__ == "__main__":
    result = run_ingestion()
    print("Ingestion complete.")
    print(f"  total chunks: {result['total_chunks']}")
    for doc, n in result["per_document"].items():
        print(f"  {doc}: {n}")
