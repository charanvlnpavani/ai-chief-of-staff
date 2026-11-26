"""OpenAI-compatible adapter: message/tool translation and stream assembly (no network)."""

import json
from types import SimpleNamespace
from typing import Any

from app.ai.openai_compat import StreamAssembler, to_openai_messages, to_openai_tools


def chunk(
    *,
    content: str | None = None,
    calls: list[Any] | None = None,
    finish: str | None = None,
    usage: Any = None,
    model: str = "m",
) -> SimpleNamespace:
    choices = (
        []
        if usage is not None and content is None and calls is None and finish is None
        else [
            SimpleNamespace(
                delta=SimpleNamespace(content=content, tool_calls=calls), finish_reason=finish
            )
        ]
    )
    return SimpleNamespace(model=model, choices=choices, usage=usage)


def call(
    index: int, *, id: str | None = None, name: str | None = None, args: str = ""
) -> SimpleNamespace:
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=args))


def test_history_translation_keeps_tool_round_trips() -> None:
    system = [{"type": "text", "text": "Be brief.", "cache_control": {"type": "ephemeral"}}]
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "What is due?"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "", "signature": "x"},
                {"type": "text", "text": "Checking."},
                {"type": "tool_use", "id": "t1", "name": "list_tasks", "input": {"due": "today"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": '{"tasks": []}'},
                {"type": "text", "text": "And tomorrow?"},
            ],
        },
    ]
    out = to_openai_messages(system, messages)
    assert out[0] == {"role": "system", "content": "Be brief."}
    assert out[1] == {"role": "user", "content": "What is due?"}
    assert out[2]["role"] == "assistant"
    assert out[2]["content"] == "Checking."  # thinking blocks are dropped
    assert out[2]["tool_calls"] == [
        {
            "id": "t1",
            "type": "function",
            "function": {"name": "list_tasks", "arguments": json.dumps({"due": "today"})},
        }
    ]
    # Tool results come right after the assistant turn, before any new user text.
    assert out[3] == {"role": "tool", "tool_call_id": "t1", "content": '{"tasks": []}'}
    assert out[4] == {"role": "user", "content": "And tomorrow?"}


def test_tool_definitions_become_functions() -> None:
    tools = [{"name": "get_goals", "description": "Goals.", "input_schema": {"type": "object"}}]
    assert to_openai_tools(tools) == [
        {
            "type": "function",
            "function": {
                "name": "get_goals",
                "description": "Goals.",
                "parameters": {"type": "object"},
            },
        }
    ]


def test_stream_assembles_text_tool_calls_and_usage() -> None:
    assembler = StreamAssembler()
    shown = [
        assembler.add(chunk(content="Let me ")),
        assembler.add(chunk(content="check.")),
        assembler.add(chunk(calls=[call(0, id="c1", name="get_goals", args='{"sta')])),
        assembler.add(chunk(calls=[call(0, args='tus": "active"}')])),
        assembler.add(chunk(finish="tool_calls")),
        assembler.add(
            chunk(
                usage=SimpleNamespace(
                    prompt_tokens=120,
                    completion_tokens=30,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=20),
                )
            )
        ),
    ]
    assert [s for s in shown if s] == ["Let me ", "check."]
    assert assembler.blocks() == [
        {"type": "text", "text": "Let me check."},
        {"type": "tool_use", "id": "c1", "name": "get_goals", "input": {"status": "active"}},
    ]
    assert assembler.stop_reason() == "tool_use"
    assert (assembler.usage.input_tokens, assembler.usage.cache_read_tokens) == (100, 20)
    assert assembler.usage.output_tokens == 30


def test_finish_reasons_and_bad_arguments() -> None:
    cut = StreamAssembler()
    cut.add(chunk(content="partial", finish="length"))
    assert cut.stop_reason() == "max_tokens"
    filtered = StreamAssembler()
    filtered.add(chunk(finish="content_filter"))
    assert filtered.stop_reason() == "refusal"
    broken = StreamAssembler()
    broken.add(chunk(calls=[call(0, id="c", name="get_goals", args="{not json")]))
    block = broken.blocks()[0]
    assert block["input"] == {"_unparsed": "{not json"}  # the tool rejects it, the loop survives
