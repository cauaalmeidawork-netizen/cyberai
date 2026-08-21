"use client";

import { useEffect, useState } from "react";

import { ProductApp } from "@/features/app/product-app";
import { createApiClient } from "@/lib/api/client";
import type { Conversation, Project } from "@/types/api";

async function ensureStarterWorkspace() {
  const client = createApiClient({ baseUrl: "" });
  const projects = await client.get<Project[]>("/api/v1/projects");

  if (projects.length > 0) {
    return;
  }

  const project = await client.post<Project>("/api/v1/projects", {
    name: "General",
    description: "Default workspace",
  });

  await client.post<Conversation>(`/api/v1/projects/${project.id}/conversations`, {
    title: "New conversation",
  });
}

function loginUrl(): string {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
  const localApi = apiBase.includes("localhost") || apiBase.includes("127.0.0.1");
  return localApi
    ? "/api/v1/auth/dev-login?return_to=%2F"
    : "/api/v1/auth/login?return_to=%2F";
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
          window.history.replaceState({}, "", currentUrl.pathname + currentUrl.search + currentUrl.hash);
        }

        if (response.ok) {
          try {
            await ensureStarterWorkspace();
          } catch {
            // ProductApp still renders manual project/conversation controls if bootstrap fails.
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
    return (
      <main className="min-h-screen bg-background text-foreground">
        <section className="mx-auto flex min-h-screen w-full max-w-md items-center justify-center px-6">
          <p className="text-sm text-muted">Connecting…</p>
        </section>
      </main>
    );
  }

  return <ProductApp />;
}
