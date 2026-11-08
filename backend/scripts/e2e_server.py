from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402

SCHEMA_PATTERN = re.compile(r"ledgerline_e2e_[0-9a-f]{12}")


def main() -> None:
    state_path = Path(os.environ["E2E_STATE_PATH"])
    state = json.loads(state_path.read_text(encoding="utf-8"))
    schema = state["schema"]
    if not isinstance(schema, str) or not SCHEMA_PATTERN.fullmatch(schema):
        raise ValueError("Invalid isolated E2E schema name")

    url = make_url(get_settings().database_url)
    query = dict(url.query)
    query["options"] = f"-csearch_path={schema}"
    os.environ["DATABASE_URL"] = url.set(query=query).render_as_string(
        hide_password=False,
    )
    os.environ["CORS_ALLOWED_ORIGINS"] = "http://127.0.0.1:15173"
    get_settings.cache_clear()

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=18000,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
