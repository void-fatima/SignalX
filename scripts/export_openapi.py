"""Run with backend's Python from the repository root."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from app.main import app

schema = app.openapi()
for path_item in schema.get("paths", {}).values():
    if not isinstance(path_item, dict):
        continue
    for operation in path_item.values():
        if not isinstance(operation, dict):
            continue
        responses = operation.get("responses")
        if isinstance(responses, dict) and isinstance(responses.get("422"), dict):
            # Python versions vary in their built-in phrase for HTTP 422.
            responses["422"]["description"] = "Unprocessable Entity"

output_path = root / "contracts" / "openapi.json"
output_path.write_text(
    json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print("Exported contracts/openapi.json")
