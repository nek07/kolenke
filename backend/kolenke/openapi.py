"""Prints the OpenAPI schema, so the frontend can generate its types without a running server:
python -m kolenke.openapi > ../frontend/src/api/openapi.json"""
import json
import os

os.environ.setdefault("KOLENKE_BACKGROUND", "false")

from kolenke.main import app  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))
