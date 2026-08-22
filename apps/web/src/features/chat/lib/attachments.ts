import type { Attachment } from "../types";

const ACCEPTED_EXTENSIONS = new Set([
  "txt",
  "md",
  "markdown",
  "json",
  "csv",
  "log",
  "yaml",
  "yml",
  "toml",
  "ini",
  "conf",
  "cfg",
  "xml",
  "sql",
  "py",
  "js",
  "ts",
  "tsx",
  "jsx",
  "go",
  "rs",
  "c",
  "h",
  "cpp",
  "hpp",
  "java",
  "kt",
  "rb",
  "php",
  "sh",
  "ps1",
  "html",
  "css",
]);

const MAX_ATTACHMENTS = 5;
const MAX_BYTES = 200_000;

export function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot + 1).toLowerCase();
}

export function isSupportedFile(name: string): boolean {
  return ACCEPTED_EXTENSIONS.has(extensionOf(name));
}

export function attachmentError(file: File, count: number): string | null {
  if (count >= MAX_ATTACHMENTS) {
    return "Limite de 5 arquivos por mensagem.";
  }
  if (!isSupportedFile(file.name)) {
    return "Tipo de arquivo não suportado.";
  }
  if (file.size > MAX_BYTES) {
    return "Arquivo muito grande (máximo 200 KB).";
  }
  return null;
}

export async function readAttachment(file: File): Promise<Attachment> {
  const content = await file.text();
  return {
    id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${file.name}`,
    name: file.name,
    size: file.size,
    content,
  };
}

export function attachmentBlock(attachment: Attachment): string {
  const fence = attachment.content.includes("```") ? "````" : "```";
  return `[Arquivo anexado: ${attachment.name}]\n${fence}\n${attachment.content}\n${fence}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
