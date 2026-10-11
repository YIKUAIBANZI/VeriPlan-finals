import { beforeEach, afterEach, vi } from "vitest";

// Tests must explicitly mock API calls; accidental fetches cannot leave the process.
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => {
    throw new Error("Unexpected network request: provide a fixture or fetch mock.");
  }));
});
afterEach(() => vi.unstubAllGlobals());
