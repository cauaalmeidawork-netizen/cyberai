"use client";

import { useState } from "react";
import { ChevronDown, Globe } from "lucide-react";

import type { SourceCitation } from "@/types/api";
import { cn } from "@/lib/utils";

function faviconFor(domain: string): string {
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=32`;
}

export function Sources({ sources }: { sources: SourceCitation[] }) {
  const [open, setOpen] = useState(false);

  if (!sources.length) {
    return null;
  }

  return (
    <div className="mt-4">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="group inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 text-xs text-foreground-muted transition-colors duration-fast hover:text-foreground"
        aria-expanded={open}
      >
        <ChevronDown
          size={14}
          aria-hidden
          className={cn(
            "transition-transform duration-fast",
            open ? "rotate-180" : "rotate-0",
          )}
        />
        <span>Fontes {sources.length}</span>
      </button>

      {open ? (
        <ul className="mt-2 grid gap-0.5">
          {sources.map((source) => (
            <li key={source.citation_index}>
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex items-start gap-3 rounded-lg px-2 py-2 transition-colors duration-fast hover:bg-surface-hover"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={faviconFor(source.domain)}
                  alt=""
                  width={16}
                  height={16}
                  className="mt-0.5 shrink-0 rounded-sm"
                  loading="lazy"
                />
                <span className="min-w-0">
                  <span className="block truncate text-sm text-foreground">
                    {source.title || source.domain}
                  </span>
                  <span className="block truncate text-xs text-foreground-faint">
                    {source.domain}
                    {source.published_at ? ` · ${source.published_at}` : ""}
                  </span>
                </span>
                <Globe
                  size={13}
                  aria-hidden
                  className="ml-auto mt-1 shrink-0 text-foreground-faint opacity-0 transition-opacity duration-fast group-hover:opacity-100"
                />
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
