"use client";

import { memo, useState, useRef } from "react";
import { Check, Copy } from "lucide-react";

import { createCodePlugin } from "@streamdown/code";
import { Streamdown, type CodeHighlighterPlugin } from "streamdown";

import type { SourceCitation } from "@/types/api";
import { linkifyCitations } from "../lib/citations";
import { cn } from "@/lib/utils";

const codePlugin = createCodePlugin({
  themes: ["github-dark", "github-dark"],
}) as unknown as CodeHighlighterPlugin;

function isSafeExternalUrl(url: string): boolean {
  try {
    const parsed = new URL(url, "about:blank");
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

export const MarkdownRenderer = memo(function MarkdownRenderer({
  content,
  streaming = false,
  sources = [],
}: {
  content: string;
  streaming?: boolean;
  sources?: SourceCitation[];
}) {
  const linkified = linkifyCitations(content, sources.length);

  return (
    <Streamdown
      mode={streaming ? "streaming" : "static"}
      parseIncompleteMarkdown
      skipHtml
      shikiTheme={["github-dark", "github-dark"]}
      plugins={{ code: codePlugin }}
      linkSafety={{
        enabled: true,
        onLinkCheck: isSafeExternalUrl,
      }}
      components={{
        pre: ({ children, ...props }) => {
          return <PreComponent {...props}>{children}</PreComponent>;
        },
        a: ({ node, href, children, ...props }) => {
          if (href?.startsWith("#citation-")) {
            const index = Number(href.slice("#citation-".length));
            const source = sources.find((entry) => entry.citation_index === index);
            if (!source) {
              return <span {...props}>{children}</span>;
            }
            return (
              <sup className="citation">
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={source.domain}
                  aria-label={`Fonte ${index}: ${source.title || source.domain}`}
                >
                  {index}
                </a>
              </sup>
            );
          }
          return (
            <a {...props} href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          );
        },
      }}
    >
      {linkified}
    </Streamdown>
  );
});

function PreComponent({ children, ...props }: React.HTMLAttributes<HTMLPreElement>) {
  const [copied, setCopied] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);

  const copy = async () => {
    if (!preRef.current) return;
    try {
      await navigator.clipboard.writeText(preRef.current.textContent || "");
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {}
  };

  const language = (props as any)["data-language"] || "Code";

  return (
    <div className="group relative my-5 overflow-hidden rounded-[14px] border border-subtle bg-background-deep shadow-sm">
      <div className="flex items-center justify-between bg-surface-1 px-4 py-2 border-b border-subtle">
        <span className="text-[11px] font-mono font-medium text-foreground-muted uppercase tracking-wider">
          {language}
        </span>
        <button
          type="button"
          onClick={copy}
          className="flex items-center gap-1.5 rounded text-[11px] font-medium text-foreground-muted hover:text-foreground transition-colors duration-fast"
        >
          {copied ? <Check size={13} className="text-accent" /> : <Copy size={13} />}
          {copied ? "Copiado" : "Copiar"}
        </button>
      </div>
      <pre
        {...props}
        ref={preRef}
        className={cn(props.className, "p-4 text-[13.5px] overflow-x-auto bg-transparent")}
      >
        {children}
      </pre>
    </div>
  );
}
