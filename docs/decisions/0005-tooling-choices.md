# ADR-0005: Tooling and version choices

- Status: accepted (2026-11-17)

| Choice | Decision | Reason |
|---|---|---|
| JS workspaces | pnpm 11 (not the brand-new 12) | stable, 7 months of patches; strict dependency isolation |
| Release-age policy | keep pnpm's minimum release age; no exclusions | blocks freshly published (possibly compromised) packages |
| Python | 3.13 via uv | broad wheel support; uv manages the interpreter and lockfile |
| DB driver | psycopg 3 | one driver for async (API) and sync (Alembic, future Celery) |
| UI kit | shadcn/ui on Radix | accessible primitives, components copied into the repo |
| Data fetching | TanStack Query on the client | pages are authenticated and personal, so no SSR data benefit |
| Charts | plain CSS bars with an accessible table | one chart in Release 1; avoids a charting dependency for now |
| Generated types | openapi-typescript with `--default-non-nullable false` | request fields with defaults stay optional |
| Local Postgres | project-local cluster on port 55432 | the existing local server requires a password; this never touches it |
| Containers | Dockerfile prepared, not built | Docker is not installed; hosting is decided in M7 |
