# ADR-0004: One approval inbox for every proposed change

- Status: accepted for Release 2+ (2026-11-17); not yet implemented

## Decision

AI proposals, email-extracted transactions, CSV imports and social publishing all become rows in a
single `approval_requests` table (source, kind, payload, payload hash, status). Nothing outside
read/suggest happens until the user approves the exact payload; applying is idempotent and
re-checks ownership and freshness. Publishing additionally binds the approval to the content
version hash and the destination account.

## Consequences

One UI, one audit trail and one tested apply path, instead of a review table per domain.
Until this exists, the AI tool registry refuses any tool above the "suggest" level.
