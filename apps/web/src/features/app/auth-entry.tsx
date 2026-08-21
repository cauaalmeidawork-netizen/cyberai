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
        if (response.status === 401) {
          window.location.replace("/api/v1/auth/login?return_to=%2F");
          return;
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
