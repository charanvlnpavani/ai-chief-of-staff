# ADR-0001: Modular monolith

- Status: accepted (2026-11-17)

## Context

One developer, eight life domains that often need each other's data (the dashboard and the AI
read across all of them), a single primary user, and a budget measured in tens of dollars a month.

## Decision

One FastAPI service and one PostgreSQL database. Each domain is a package under
`app/modules/<name>` with its own models, schemas, service and router. Modules use each other only
through `service`, `schemas` or `ai_tools`; `tests/test_architecture.py` fails the build otherwise.

## Consequences

- Cross-domain features are simple function calls and single transactions.
- One process to deploy, monitor and back up.
- Module boundaries keep the option of extracting a service later if a real need appears.
- Rejected: microservices (operational cost with no benefit at this scale).
