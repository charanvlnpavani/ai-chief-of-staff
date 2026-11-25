# ADR-0003: Self-hosted AI tool loop on the Messages API

- Status: accepted (2026-11-17)

## Context

The Chief of Staff needs Claude to call tools that read the user's records. Requirements: data
stays under the user's control, authorization is enforced in code, every action is auditable,
costs are capped, and there is no unnecessary infrastructure or lock-in.

## Options

1. **Anthropic Managed Agents.** Anthropic hosts the agent loop and a per-session container. It
   is beta, bills session runtime on top of tokens, and keeps session history on Anthropic's side
   until deleted. The container is unnecessary here, because every tool is a call into our own
   backend.
2. **Self-hosted loop on the Messages API**, using the official Python SDK in FastAPI.

## Decision

Option 2: a manual loop (`app/ai/orchestrator.py`) rather than the SDK's beta Tool Runner, because
each iteration must run budget checks, write audit and ledger rows, and stream SSE events. The
model client sits behind a small `ChatModel` interface, so tests use a scripted fake (no cost).

## Consequences

- Conversation history lives encrypted in our database; only the minimum needed per request is sent.
- We own retries, timeouts and the stop-reason handling (covered by tests).
- Revisit Managed Agents if long-running autonomous research jobs are ever wanted.
