import os
import sys

# Make the project root importable so `import app...` works in tests.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Keep tests offline: deterministic-core tests never touch Gemini or Postgres.
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mna")
