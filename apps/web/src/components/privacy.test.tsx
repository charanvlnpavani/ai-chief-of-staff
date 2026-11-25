import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Private, PrivacyProvider, usePrivacy } from "./privacy";

function Toggle() {
  const { toggle } = usePrivacy();
  return (
    <button type="button" onClick={toggle}>
      toggle
    </button>
  );
}

describe("Private", () => {
  it("shows values normally and masks them in privacy mode", () => {
    render(
      <PrivacyProvider>
        <Private>₹12,345</Private>
        <Toggle />
      </PrivacyProvider>,
    );
    expect(screen.getByText("₹12,345")).toBeInTheDocument();
    act(() => screen.getByRole("button").click());
    expect(screen.queryByText("₹12,345")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Hidden by privacy mode")).toBeInTheDocument();
  });
});
