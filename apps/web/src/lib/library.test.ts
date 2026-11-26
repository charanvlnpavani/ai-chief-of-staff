import { describe, expect, it } from "vitest";

import { duplicateId, parseCapture, parseTags, savedLabel, sharedCapture } from "@/lib/library";

describe("parseCapture", () => {
  it.each([
    "https://example.com/post",
    "http://example.com",
    "example.com/post?x=1",
    "www.youtube.com/watch?v=dQw4w9WgXcQ",
    "  youtu.be/dQw4w9WgXcQ  ",
  ])("treats a lone address as a link: %s", (input) => {
    expect(parseCapture(input)).toEqual({ kind: "link", url: input.trim() });
  });

  it.each([
    "Buy milk",
    "Read example.com later", // an address inside a sentence stays a note
    "v1.2",
    "3.14",
    "e.g.",
    "@someone.handle",
    "line one\nexample.com",
  ])("treats other text as a note: %s", (input) => {
    expect(parseCapture(input)).toEqual({ kind: "note", body: input.trim() });
  });

  it("ignores blank input", () => {
    expect(parseCapture("   \n ")).toBeNull();
  });
});

describe("sharedCapture", () => {
  it("prefers the shared url", () => {
    expect(sharedCapture({ title: "T", text: "see https://a.test/x", url: "https://b.test" })).toBe("https://b.test");
  });

  it("finds a link inside shared text", () => {
    expect(sharedCapture({ title: "Post", text: "Look at this https://a.test/x?y=1 wow" })).toBe("https://a.test/x?y=1");
  });

  it("falls back to title and text as a note", () => {
    expect(sharedCapture({ title: "Idea", text: "Write more" })).toBe("Idea\nWrite more");
    expect(sharedCapture({})).toBe("");
  });
});

describe("parseTags", () => {
  it("splits on commas, strips #, drops blanks and case repeats", () => {
    expect(parseTags("Python, rust ,, #Go, python, ##")).toEqual(["Python", "rust", "Go"]);
  });
});

describe("duplicateId", () => {
  it("reads the existing id from a duplicate problem", () => {
    expect(duplicateId({ code: "library_duplicate", existingId: "abc" })).toBe("abc");
    expect(duplicateId({ code: "version_conflict", existingId: "abc" })).toBeNull();
    expect(duplicateId(undefined)).toBeNull();
  });
});

describe("savedLabel", () => {
  it("omits the year for this year", () => {
    const now = new Date(2026, 10, 26);
    expect(savedLabel(new Date(2026, 2, 1).toISOString(), now)).not.toMatch(/2026/);
    expect(savedLabel(new Date(2025, 2, 1).toISOString(), now)).toMatch(/2025/);
  });
});
