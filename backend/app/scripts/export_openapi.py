"""Write the OpenAPI schema to a file (or stdout). Used to generate the TypeScript client.

uv run python -m app.scripts.export_openapi ../packages/api-client/openapi.json
"""

import json
import sys
from pathlib import Path

from app.main import create_app


def main() -> None:
    schema = create_app().openapi()
    text = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text, encoding="utf-8")
        print(f"wrote {sys.argv[1]}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
