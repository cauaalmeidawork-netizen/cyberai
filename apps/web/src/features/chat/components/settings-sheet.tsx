"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, LogOut, X } from "lucide-react";

import { createApiClient } from "@/lib/api/client";
import { APP_VERSION } from "@/lib/config";
import type { AuthMe, BillingUsage } from "@/types/api";
import { planLabel, quotaLabel, roleLabel } from "../labels";
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
    const getFocusableItems = () =>
      Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => !element.hasAttribute("disabled"));

    getFocusableItems()[0]?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const items = getFocusableItems();
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

  const membership =
    authInfo?.organizations.find((org) => org.org_id === authInfo.active_org_id) ?? null;
  const displayName = authInfo?.user_display_name ?? membership?.org_display_name ?? null;
  const role = membership?.role ?? authInfo?.role ?? null;

  const requestsQuota = usage?.usage.find((quota) => quota.resource === "requests") ?? null;
  const technicalQuotas = (usage?.usage ?? []).filter((quota) => quota.resource !== "requests");
  const nearLimit =
    requestsQuota !== null && requestsQuota.limit > 0
      ? requestsQuota.used / requestsQuota.limit >= 0.9
      : false;

  return (
    <div
      className="fixed inset-0 z-[var(--z-modal)] flex justify-end bg-black/40"
      onClick={onClose}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Configurações"
        onClick={(event) => event.stopPropagation()}
        className="animate-sheet-in flex h-full w-full max-w-[420px] flex-col border-l border-hairline bg-background-deep shadow-2xl"
      >
        <div className="flex items-center gap-2 px-5 py-3.5">
          <NomercyMark className="size-[18px] text-accent" />
          <h2 className="text-[15px] font-medium tracking-tight text-foreground">Configurações</h2>
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

        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-8">
          {/* Conta */}
          <section className="border-b border-hairline py-5">
            <h3 className="mb-3 text-[11px] font-medium uppercase tracking-[0.12em] text-foreground-faint">
              Conta
            </h3>
            {displayName ? (
              <p className="text-[15px] font-medium text-foreground-strong">{displayName}</p>
            ) : null}
            {authInfo?.user_email ? (
              <p className="mt-0.5 text-[13px] text-foreground-muted">{authInfo.user_email}</p>
            ) : null}
            <div className={cn("grid gap-1.5", displayName || authInfo?.user_email ? "mt-4" : "")}>
              <Row label="Organização" value={membership?.org_display_name} />
              <Row label="Função" value={role ? roleLabel(role) : undefined} />
            </div>
            <button
              type="button"
              onClick={onLogout}
              className="mt-4 inline-flex items-center gap-1.5 rounded-md text-[13px] text-foreground-muted transition-colors duration-fast hover:text-danger"
            >
              <LogOut size={14} aria-hidden />
              Sair
            </button>
          </section>

          {/* Plano */}
          <section className="border-b border-hairline py-5">
            <h3 className="mb-3 text-[11px] font-medium uppercase tracking-[0.12em] text-foreground-faint">
              Plano
            </h3>
            {canReadBilling && usage ? (
              <>
                <Row label="Plano" value={planLabel(usage.plan)} />
                {requestsQuota && requestsQuota.limit > 0 ? (
                  <div className="mt-4">
                    <p className="text-[13px] text-foreground-muted">
                      {requestsQuota.used.toLocaleString("pt-BR")} de{" "}
                      {requestsQuota.limit.toLocaleString("pt-BR")} mensagens usadas
                    </p>
                    <div className="mt-2 h-[3px] overflow-hidden rounded-full bg-surface-2">
                      <div
                        className={cn(
                          "h-full rounded-full transition-[width] duration-slow",
                          nearLimit ? "bg-accent" : "bg-foreground-muted",
                        )}
                        style={{
                          width: `${Math.min(100, (requestsQuota.used / requestsQuota.limit) * 100)}%`,
                        }}
                      />
                    </div>
                  </div>
                ) : null}
                {technicalQuotas.length > 0 ? (
                  <details className="group mt-4">
                    <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-[13px] text-foreground-faint transition-colors duration-fast hover:text-foreground-muted">
                      Detalhes técnicos
                      <ChevronDown
                        size={13}
                        aria-hidden
                        className="transition-transform duration-fast group-open:rotate-180"
                      />
                    </summary>
                    <div className="mt-3 grid gap-1.5">
                      {technicalQuotas.map((quota) => (
                        <Row
                          key={quota.resource}
                          label={quotaLabel(quota.resource)}
                          value={`${quota.used.toLocaleString("pt-BR")} / ${quota.limit.toLocaleString("pt-BR")}`}
                        />
                      ))}
                    </div>
                  </details>
                ) : null}
              </>
            ) : (
              <p className="text-[13px] text-foreground-faint">
                Informações de uso não disponíveis.
              </p>
            )}
          </section>

          {/* Sobre */}
          <section className="py-5">
            <h3 className="mb-3 text-[11px] font-medium uppercase tracking-[0.12em] text-foreground-faint">
              Sobre
            </h3>
            <Row label="Produto" value="Nomercy AI" />
            <Row label="Versão" value={APP_VERSION} />
            <p className="mt-4 text-[13px] text-foreground-faint">
              Assistente de pesquisa e análise técnica.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className="text-[13px] text-foreground-muted">{label}</span>
      <span className="truncate text-right text-[13px] text-foreground">{value ?? "—"}</span>
    </div>
  );
}
