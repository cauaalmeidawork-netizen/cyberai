import { describe, expect, it } from "vitest";

import { attachmentBlock, attachmentError, extensionOf, formatBytes, isSupportedFile } from "./attachments";

function fakeFile(name: string, size: number): File {
  return new File([new Array(size).fill("a").join("")], name, { type: "text/plain" });
}

describe("attachment helpers", () => {
  it("detects supported extensions", () => {
    expect(isSupportedFile("report.log")).toBe(true);
    expect(isSupportedFile("script.py")).toBe(true);
    expect(isSupportedFile("data.csv")).toBe(true);
    expect(isSupportedFile("evil.exe")).toBe(false);
  });

  it("computes the extension", () => {
    expect(extensionOf("a.b.log")).toBe("log");
    expect(extensionOf("noext")).toBe("");
  });

  it("rejects too many attachments", () => {
    expect(attachmentError(fakeFile("a.txt", 10), 5)).toBe("Limite de 5 arquivos por mensagem.");
  });

  it("rejects oversized files", () => {
    expect(attachmentError(fakeFile("big.txt", 300_000), 0)).toBe(
      "Arquivo muito grande (máximo 200 KB).",
    );
  });

  it("renders an attachment block with a fenced code block", () => {
    const block = attachmentBlock({ id: "1", name: "a.log", size: 3, content: "abc" });
    expect(block).toContain("[Arquivo anexado: a.log]");
    expect(block).toContain("```");
    expect(block).toContain("abc");
  });

  it("formats byte sizes", () => {
    expect(formatBytes(500)).toBe("500 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
  });
});
