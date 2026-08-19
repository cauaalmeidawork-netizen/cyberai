"use client";

import { useEffect, useState } from "react";

interface HealthStatus {
  status: string;
  service: string;
  version: string;
  environment: string;
}

interface DependencyStatus {
  name: string;
  healthy: boolean;
  detail?: string;
}

interface ReadinessStatus {
  status: string;
  dependencies: DependencyStatus[];
}

export function StatusPanel() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [ready, setReady] = useState<ReadinessStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchStatus() {
      try {
        const [healthRes, readyRes] = await Promise.all([
          fetch("/healthz"),
          fetch("/readyz"),
        ]);
        setHealth(await healthRes.json());
        setReady(await readyRes.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch status");
      }
    }
    fetchStatus();
  }, []);

  return (
    <section className="w-full max-w-2xl rounded-xl border border-border bg-card p-6 shadow-lg">
      <h2 className="text-xl font-semibold mb-4">Platform Status</h2>
      {error && <p className="text-red-400">{error}</p>}
      {health && (
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-muted">Service</dt>
            <dd className="font-medium">{health.service}</dd>
          </div>
          <div>
            <dt className="text-muted">Version</dt>
            <dd className="font-medium">{health.version}</dd>
          </div>
          <div>
            <dt className="text-muted">Environment</dt>
            <dd className="font-medium">{health.environment}</dd>
          </div>
          <div>
            <dt className="text-muted">Liveness</dt>
            <dd className="font-medium text-emerald-400">{health.status}</dd>
          </div>
        </dl>
      )}
      {ready && (
        <div className="mt-6 space-y-2">
          <h3 className="text-sm font-medium text-muted">Dependencies</h3>
          <ul className="space-y-2">
            {ready.dependencies.map((dep) => (
              <li
                key={dep.name}
                className="flex items-center justify-between rounded-lg border border-border px-4 py-2"
              >
                <span className="text-sm font-medium">{dep.name}</span>
                <span
                  className={`text-xs font-semibold px-2 py-1 rounded-full ${
                    dep.healthy
                      ? "bg-emerald-500/10 text-emerald-400"
                      : "bg-red-500/10 text-red-400"
                  }`}
                >
                  {dep.healthy ? "healthy" : "unhealthy"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
