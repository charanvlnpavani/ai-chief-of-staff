# Personal OS API

FastAPI modular monolith. See the repository README for setup.

```bash
uv sync                         # install
uv run uvicorn app.main:app --reload --port 8000
uv run pytest                   # needs the dev Postgres (scripts/dev-db.sh start)
uv run ruff check . && uv run ruff format --check . && uv run mypy app
uv run alembic revision --autogenerate -m "describe change"   # then review by hand
```

Interactive API docs (non-production only): http://localhost:8000/api/docs

## Module anatomy

Each domain in `app/modules/<name>/` has `models.py`, `schemas.py`, `service.py`, `router.py` and,
where useful, `ai_tools.py`. Routers handle HTTP; services hold business rules and commit
transactions; modules use each other only through `service`, `schemas` or `ai_tools`
(enforced by `tests/test_architecture.py`).
