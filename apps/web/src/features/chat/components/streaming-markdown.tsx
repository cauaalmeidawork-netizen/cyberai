"use client";

import { lazy, memo, Suspense } from "react";

import type { SourceCitation } from "@/types/api";

const MarkdownRenderer = lazy(() =>
  import("./markdown-renderer").then((module) => ({ default: module.MarkdownRenderer })),
);

export const StreamingMarkdown = memo(function StreamingMarkdown({
  content,
  streaming = false,
  sources = [],
}: {
  content: string;
  streaming?: boolean;
  sources?: SourceCitation[];
}) {
  if (!content) {
    return null;
  }
  return (
    <Suspense fallback={<div className="text-foreground-faint">{content}</div>}>
      <MarkdownRenderer content={content} streaming={streaming} sources={sources} />
    </Suspense>
  );
});
