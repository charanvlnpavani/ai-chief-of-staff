import { describe, expect, it } from "vitest";

import { parseFrame, readSse, type SseEvent } from "./sse";

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(chunks: string[]): Promise<SseEvent[]> {
  const events: SseEvent[] = [];
  for await (const event of readSse(streamOf(chunks))) events.push(event);
  return events;
}

describe("parseFrame", () => {
  it("parses event name and JSON data", () => {
    expect(parseFrame('event: text\ndata: {"delta":"Hi"}')).toEqual({ event: "text", data: { delta: "Hi" } });
  });

  it("defaults the event name and ignores frames without data", () => {
    expect(parseFrame("data: 1")).toEqual({ event: "message", data: 1 });
    expect(parseFrame(": comment only")).toBeNull();
  });
});

describe("readSse", () => {
  it("reassembles frames split across network chunks", async () => {
    const events = await collect([
      'event: start\ndata: {"conversationId":"c1"}\n\nevent: te',
      'xt\ndata: {"delta":"Hel',
      'lo"}\n\nevent: done\ndata: {"costUsd":0.01}\n\n',
    ]);
    expect(events.map((e) => e.event)).toEqual(["start", "text", "done"]);
    expect(events[1].data).toEqual({ delta: "Hello" });
  });

  it("handles CRLF line endings and a final frame without a trailing blank line", async () => {
    const events = await collect(['event: text\r\ndata: {"delta":"a"}\r\n\r\n', 'event: done\ndata: {}']);
    expect(events).toEqual([
      { event: "text", data: { delta: "a" } },
      { event: "done", data: {} },
    ]);
  });
});
