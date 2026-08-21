export const AUTH_SESSION_KEY = "cyberai.auth.bearer_token";

export interface SessionAuthStore {
  getToken(): string | null;
  setToken(token: string): void;
  clear(): void;
}

export function createSessionAuthStore(): SessionAuthStore {
  return {
    getToken() {
      return getBrowserSessionStorage()?.getItem(AUTH_SESSION_KEY) ?? null;
    },
    setToken(token: string) {
      const storage = getBrowserSessionStorage();
      if (!storage) {
        return;
      }
      const trimmed = token.trim();
      if (trimmed.length === 0) {
        storage.removeItem(AUTH_SESSION_KEY);
        return;
      }
      storage.setItem(AUTH_SESSION_KEY, trimmed);
    },
    clear() {
      getBrowserSessionStorage()?.removeItem(AUTH_SESSION_KEY);
    },
  };
}

function getBrowserSessionStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.sessionStorage;
}
