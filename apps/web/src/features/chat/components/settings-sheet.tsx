"use client";

import { useEffect, useRef, useState } from "react";
import { LogOut, X } from "lucide-react";

import { createApiClient } from "@/lib/api/client";
import type { AuthMe, BillingUsage } from "@/types/api";
import { NomercyMark } from "./mark";
import { cn } from "@/lib/utils";

export function SettingsSheet({
  open,
  onClose,
  authInfo,
  onLogout,
}: {
  open: boolean;
  onClose: () => void;
  authInfo: AuthMe | null;
  onLogout: () => void;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [usage, setUsage] = useState<BillingUsage | null>(null);

  const canReadBilling = authInfo?.permissions.includes("billing.read") ?? false;

  useEffect(() => {
    if (!open || !canReadBilling) return;

    let cancelled = false;
    createApiClient({ baseUrl: "" })
      .get<BillingUsage>("/api/v1/billing/usage")
      .then((result) => {
        if (!cancelled) setUsage(result);
      })
      .catch(() => {
        // Usage is optional in Settings; silently omit on failure.
      });
    return () => {
      cancelled = true;
    };
  }, [open, canReadBilling]);

  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    const focusables = panel.querySelectorAll<HTMLElement>(
      'button, [href], input, [tabindex]:not([tabindex="-1"])',
    );
    focusables[0]?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const items = Array.from(focusables).filter((el) => !el.hasAttribute("disabled"));
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    panel.addEventListener("keydown", handleKeyDown);
    return () => {
      panel.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  const organization =
    authInfo?.organizations.find((org) => org.org_id === authInfo.active_org_id) ?? null;

  return (
    <div
      className="fixed inset-0 z-[var(--z-modal)] flex justify-end bg-black/50 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Configurações"
        onClick={(event) => event.stopPropagation()}
        className="flex h-full w-full max-w-sm flex-col border-l border-subtle bg-background-deep shadow-2xl"
      >
        <div className="flex items-center gap-2 border-b border-subtle px-4 py-3">
          <NomercyMark className="size-5 text-accent" />
          <h2 className="text-sm font-semibold tracking-tight text-foreground">Configurações</h2>
          <button
            type="button"
            onClick={onClose}
            title="Fechar"
            aria-label="Fechar configurações"
            className="ml-auto grid size-8 place-items-center rounded-lg text-foreground-muted transition-colors duration-fast hover:bg-surface-hover hover:text-foreground"
          >
            <X size={16} aria-hidden />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
          <Section title="Conta">
            <Row label="Organização" value={organization?.org_display_name ?? "—"} />
            <Row label="Função" value={authInfo?.role ?? "—"} />
            <button
              type="button"
              onClick={onLogout}
              className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-subtle bg-surface-1 px-3 py-2 text-sm text-foreground transition-colors duration-fast hover:border-danger hover:text-danger"
            >
              <LogOut size={15} aria-hidden />
              Sair
            </button>
          </Section>

          <Section title="Uso">
            {canReadBilling && usage ? (
              <dl className="grid gap-2">
                <Row label="Plano" value={usage.plan} />
                {usage.usage.map((quota) => (
                  <Row
                    key={quota.resource}
                    label={resourceLabel(quota.resource)}
                    value={`${quota.used.toLocaleString()} / ${quota.limit.toLocaleString()}`}
                  />
                ))}
              </dl>
            ) : (
              <p className="text-xs text-foreground-faint">Informações de uso não disponíveis.</p>
            )}
          </Section>

          <Section title="Sobre">
            <Row label="Produto" value="Nomercy AI" />
            <p className="mt-2 text-xs leading-relaxed text-foreground-muted">
              Uma IA conversacional especialista em cybersecurity: pesquisa fontes públicas,
              cruza informação e responde com citações. Consultiva — nunca executa comandos.
            </p>
          </Section>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-6">
      <h3 className="mb-2 text-[11px] font-medium uppercase tracking-wider text-foreground-faint">
        {title}
      </h3>
      <div className="rounded-xl border border-subtle bg-surface-1 px-3 py-2.5">{children}</div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-1">
      <dt className="text-xs text-foreground-muted">{label}</dt>
      <dd className={cn("truncate text-right text-xs text-foreground")}>{value}</dd>
    </div>
  );
}

function resourceLabel(resource: string): string {
  switch (resource) {
    case "requests":
      return "Requisições";
    case "input_tokens":
      return "Tokens de entrada";
    case "output_tokens":
      return "Tokens de saída";
    case "total_tokens":
      return "Tokens totais";
    default:
      return resource;
  }
}
