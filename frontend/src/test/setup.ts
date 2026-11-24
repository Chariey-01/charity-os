import "@testing-library/jest-dom/vitest";

import { configure } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { NOW } from "./mockApi";

// Full-app renders can exceed the 1s default when the suite runs in parallel.
configure({ asyncUtilTimeout: 4000 });

beforeEach(() => {
  // Only Date is faked so React and Testing Library timers keep running.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  window.location.hash = "";
  localStorage.clear();
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});
