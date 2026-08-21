"use client";

import { useEffect, useState } from "react";

import { ProductApp } from "@/features/app/product-app";

export function AuthEntry() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    void fetch("/api/v1/auth/me", {
      credentials: "include",
      headers: { Accept: "application/json" },
    })
      .then((response) => {
        if (cancelled) return;

        const currentUrl = new URL(window.location.href);
        const returnedFromAuth = currentUrl.searchParams.get("_auth") === "1";

        if (response.status === 401 && !returnedFromAuth) {
          window.location.replace("/api/v1/auth/login?return_to=%2F");
          return;
        }

        if (returnedFromAuth) {
          currentUrl.searchParams.delete("_auth");
          window.history.replaceState({}, "", currentUrl.pathname + currentUrl.search + currentUrl.hash);
        }

        setReady(true);
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
