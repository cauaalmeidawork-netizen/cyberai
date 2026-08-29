"use client";

import { memo } from "react";

import { createCodePlugin } from "@streamdown/code";
import { Streamdown, type CodeHighlighterPlugin } from "streamdown";

import type { SourceCitation } from "@/types/api";
import { linkifyCitations } from "../lib/citations";

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
