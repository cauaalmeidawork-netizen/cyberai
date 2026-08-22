"use client";

import { useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

import type { ModelInfo } from "@/types/api";
import { cn } from "@/lib/utils";

export function ModelPicker({
  models,
  value,
  onChange,
}: {
  models: ModelInfo[];
  value: string;
  onChange: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const selected = models.find((model) => model.key === value);
  if (models.length === 0) {
    return null;
  }

  const isInteractive = models.length > 1;

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => isInteractive && setOpen((current) => !current)}
        onBlur={(event) => {
          if (!containerRef.current?.contains(event.relatedTarget as Node)) {
            setOpen(false);
          }
        }}
        disabled={!isInteractive}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[13px] text-foreground-muted transition-colors duration-fast",
          isInteractive && "hover:bg-surface-hover hover:text-foreground",
          !isInteractive && "cursor-default"
        )}
        aria-haspopup={isInteractive ? "listbox" : undefined}
        aria-expanded={isInteractive ? open : undefined}
      >
        <span className="max-w-[140px] truncate">{selected?.display_name ?? "Modelo"}</span>
        {isInteractive && (
          <ChevronDown
            size={13}
            aria-hidden
            className={cn("transition-transform duration-fast text-foreground-faint", open && "rotate-180")}
          />
        )}
      </button>

      {open && isInteractive ? (
        <ul
          role="listbox"
          className="absolute bottom-full right-0 z-50 mb-2 min-w-[180px] overflow-hidden rounded-[14px] border border-subtle bg-surface-2 p-1.5 shadow-[0_8px_40px_rgba(0,0,0,0.4)]"
        >
          {models.map((model) => (
            <li key={model.key}>
              <button
                type="button"
                role="option"
                aria-selected={model.key === value}
                onClick={() => {
                  onChange(model.key);
                  setOpen(false);
                }}
                className={cn(
                  "flex w-full items-center justify-between gap-3 rounded-[10px] px-3 py-2 text-left text-[13px] transition-colors duration-fast hover:bg-surface-hover",
                  model.key === value ? "text-foreground" : "text-foreground-muted",
                )}
              >
                <span className="block truncate">{model.display_name}</span>
                {model.key === value ? <Check size={14} className="text-accent shrink-0" /> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
