import { describe, expect, it } from "vitest";

import { addDays, daysBetween, dueLabel, formatMinutes, greeting, percent } from "./format";

describe("formatMinutes", () => {
  it.each([
    [0, "0m"],
    [45, "45m"],
    [60, "1h"],
    [90, "1h 30m"],
    [-5, "0m"],
  ])("%i -> %s", (minutes, expected) => {
    expect(formatMinutes(minutes)).toBe(expected);
  });
});

describe("dates", () => {
  it("adds days across month and year boundaries", () => {
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });

  it("counts calendar days, not 24-hour periods", () => {
    // 2026-03-08 is a DST change in many zones; calendar maths must still give 1.
    expect(daysBetween("2026-03-07", "2026-03-08")).toBe(1);
  });

  it("labels due dates relative to today", () => {
    const today = "2026-11-17";
    expect(dueLabel(null, today)).toBeNull();
    expect(dueLabel("2026-11-17", today)).toBe("Today");
    expect(dueLabel("2026-11-18", today)).toBe("Tomorrow");
    expect(dueLabel("2026-11-16", today)).toBe("Yesterday");
    expect(dueLabel("2026-11-14", today)).toBe("3 days overdue");
  });
});

describe("misc", () => {
  it("formats percentages and greetings", () => {
    expect(percent(0.667)).toBe("67%");
    expect(percent(null)).toBe("—");
    expect(greeting(8)).toBe("Good morning");
    expect(greeting(20)).toBe("Good evening");
  });
});
