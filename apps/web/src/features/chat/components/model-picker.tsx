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

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        onBlur={(event) => {
          if (!containerRef.current?.contains(event.relatedTarget as Node)) {
            setOpen(false);
          }
        }}
        className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-foreground-muted transition-colors duration-fast hover:bg-surface-hover hover:text-foreground"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="max-w-[140px] truncate">{selected?.display_name ?? "Modelo"}</span>
        <ChevronDown
          size={12}
          aria-hidden
          className={cn("transition-transform duration-fast", open && "rotate-180")}
        />
      </button>

      {open ? (
        <ul
          role="listbox"
          className="absolute bottom-full left-0 z-50 mb-2 min-w-[200px] overflow-hidden rounded-lg border border-subtle bg-surface-2 p-1 shadow-lg"
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
                  "flex w-full items-center justify-between gap-3 rounded-md px-2.5 py-2 text-left text-sm transition-colors duration-fast hover:bg-surface-hover",
                  model.key === value ? "text-foreground" : "text-foreground-muted",
                )}
              >
                <span>
                  <span className="block">{model.display_name}</span>
                  <span className="block truncate text-[11px] text-foreground-faint">
                    {model.description}
                  </span>
                </span>
                {model.key === value ? <Check size={14} className="text-accent" /> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
