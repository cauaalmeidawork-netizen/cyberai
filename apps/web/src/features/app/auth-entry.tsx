"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/features/chat/components/app-shell";
import { createApiClient } from "@/lib/api/client";
import type { Project } from "@/types/api";

async function ensureStarterWorkspace() {
  const client = createApiClient({ baseUrl: "" });
  const projects = await client.get<Project[]>("/api/v1/projects");
  if (projects.length > 0) {
    return;
  }
  await client.post<Project>("/api/v1/projects", {
    name: "Geral",
    description: null,
  });
}

export function loginUrlForEnvironment(
  apiBase: string,
  nodeEnv: string | undefined = process.env.NODE_ENV,
): string {
  const localApi =
    nodeEnv === "development" &&
    (!apiBase || apiBase.includes("localhost") || apiBase.includes("127.0.0.1"));
  return localApi
    ? "/api/v1/auth/dev-login?return_to=%2F"
    : "/api/v1/auth/login?return_to=%2F";
}

function loginUrl(): string {
  return loginUrlForEnvironment(process.env.NEXT_PUBLIC_API_BASE_URL ?? "");
}

export function AuthEntry() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    void fetch("/api/v1/auth/me", {
      credentials: "include",
      headers: { Accept: "application/json" },
    })
      .then(async (response) => {
        if (cancelled) return;

        const currentUrl = new URL(window.location.href);
        const returnedFromAuth = currentUrl.searchParams.get("_auth") === "1";

        if (response.status === 401 && !returnedFromAuth) {
          window.location.replace(loginUrl());
          return;
        }

        if (returnedFromAuth) {
          currentUrl.searchParams.delete("_auth");
          window.history.replaceState(
            {},
            "",
            currentUrl.pathname + currentUrl.search + currentUrl.hash,
          );
        }

        if (response.ok) {
          try {
            await ensureStarterWorkspace();
          } catch {
            // AppShell still renders if bootstrap fails.
          }
        }

        if (!cancelled) {
          setReady(true);
        }
      })
      .catch(() => {
        if (!cancelled) setReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (!ready) {
    return null;
  }

  return <AppShell />;
}
