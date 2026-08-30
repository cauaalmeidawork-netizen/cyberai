"use client";

import { useLayoutEffect, useRef } from "react";
import { ArrowUp, FileText, Plus, Square, X } from "lucide-react";

import type { ModelInfo } from "@/types/api";
import type { Attachment } from "../types";
import { ModelPicker } from "./model-picker";
import { cn } from "@/lib/utils";

export function Composer({
  draft,
  onChange,
  onSend,
  isSending,
  onStop,
  models,
  selectedModel,
  onSelectModel,
  disabled,
  attachments,
  onAttach,
  onRemoveAttachment,
}: {
  draft: string;
  onChange: (value: string) => void;
  onSend: () => void;
  isSending: boolean;
  onStop: () => void;
  models: ModelInfo[];
  selectedModel: string;
  onSelectModel: (key: string) => void;
  disabled?: boolean;
  attachments: Attachment[];
  onAttach: (files: FileList | File[]) => void;
  onRemoveAttachment: (id: string) => void;
}) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }, [draft]);

  const canSend = (Boolean(draft.trim()) || attachments.length > 0) && !isSending;

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (canSend) {
        onSend();
      }
    }
  };

  return (
    <div className="flex shrink-0 justify-center px-3 pb-3 pt-1 sm:px-6 sm:pb-5">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (canSend) onSend();
        }}
        className="relative flex w-full max-w-composer flex-col rounded-[16px] bg-surface-raised shadow-[0_2px_20px_rgba(0,0,0,0.34),0_0_0_1px_oklch(0.28_0.015_262/0.2)]"
      >
        {attachments.length > 0 ? (
          <div className="flex flex-wrap gap-2 px-3.5 pt-3">
            {attachments.map((attachment) => (
              <span
                key={attachment.id}
                className="inline-flex items-center gap-1.5 rounded-md bg-surface-2 px-2 py-1 text-xs text-foreground-muted"
              >
                <FileText size={13} aria-hidden className="text-foreground-faint" />
                <span className="max-w-[180px] truncate">{attachment.name}</span>
                <button
                  type="button"
                  onClick={() => onRemoveAttachment(attachment.id)}
                  title="Remover anexo"
                  aria-label={`Remover ${attachment.name}`}
                  className="grid size-4 place-items-center rounded text-foreground-faint transition-colors duration-fast hover:text-foreground"
                >
                  <X size={12} aria-hidden />
                </button>
              </span>
            ))}
          </div>
        ) : null}

        <div className="flex items-end gap-1 px-2 py-2">
          <div className="flex h-10 shrink-0 items-center">
            <button
              type="button"
              title="Anexar arquivo"
              aria-label="Anexar arquivo"
              onClick={() => fileInputRef.current?.click()}
              className="grid size-8 place-items-center rounded-lg text-foreground-faint transition-colors duration-fast hover:bg-surface-hover hover:text-foreground active:scale-95"
            >
              <Plus size={16} aria-hidden />
            </button>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            hidden
            onChange={(event) => {
              if (event.target.files?.length) {
                void onAttach(event.target.files);
              }
              event.target.value = "";
            }}
            accept=".txt,.md,.markdown,.json,.csv,.log,.yaml,.yml,.toml,.ini,.conf,.cfg,.xml,.sql,.py,.js,.ts,.tsx,.jsx,.go,.rs,.c,.h,.cpp,.hpp,.java,.kt,.rb,.php,.sh,.ps1,.html,.css"
          />

          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Pergunte ao Nomercy"
            disabled={disabled}
            rows={1}
            className="max-h-40 min-h-[40px] w-full min-w-0 flex-1 resize-none bg-transparent py-[9px] text-[15px] leading-[22px] text-foreground placeholder:text-foreground-faint focus:outline-none disabled:opacity-50"
          />

          <div className="flex h-10 shrink-0 items-center gap-1 pr-1">
            <ModelPicker models={models} value={selectedModel} onChange={onSelectModel} />
            {isSending ? (
              <button
                type="button"
                onClick={onStop}
                title="Parar geração"
                aria-label="Parar geração"
                className="grid size-8 place-items-center rounded-[10px] bg-surface-2 text-foreground transition-all duration-fast hover:bg-surface-hover active:scale-95"
              >
                <Square size={11} aria-hidden />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!canSend}
                title="Enviar"
                aria-label="Enviar mensagem"
                className={cn(
                  "grid size-8 place-items-center rounded-[10px] transition-all duration-fast active:scale-95",
                  canSend
                    ? "bg-accent text-accent-foreground hover:bg-accent-hover shadow-[0_0_14px_oklch(0.585_0.215_25/0.35)]"
                    : "text-foreground-faint",
                )}
              >
                <ArrowUp size={15} aria-hidden />
              </button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
