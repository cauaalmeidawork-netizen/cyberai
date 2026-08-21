import { describe, expect, it, beforeEach, vi } from "vitest";

import { AUTH_SESSION_KEY, createSessionAuthStore } from "./session";

describe("session auth store", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("stores externally supplied bearer tokens in sessionStorage only", () => {
    const store = createSessionAuthStore();

    store.setToken("external-token");

    expect(store.getToken()).toBe("external-token");
    expect(sessionStorage.getItem(AUTH_SESSION_KEY)).toBe("external-token");
    expect(localStorage.getItem(AUTH_SESSION_KEY)).toBeNull();
  });

  it("clears the token immediately on logout", () => {
    const store = createSessionAuthStore();
    store.setToken("external-token");

    store.clear();

    expect(store.getToken()).toBeNull();
    expect(sessionStorage.getItem(AUTH_SESSION_KEY)).toBeNull();
  });
});
