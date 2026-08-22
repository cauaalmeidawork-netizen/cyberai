import { cn } from "@/lib/utils";

export function NomercyMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className={cn("block", className)}
      fill="none"
    >
      <path d="M4 20V4h3.5l5 9.5V4h3.5v16h-3.5l-5-9.5V20H4z" fill="currentColor" />
      {/* M Right connection (Accent) */}
      <path d="M12.5 13.5l4-7.5h3.5v14h-3.5v-7.5l-4 7.5z" fill="var(--accent)" />
    </svg>
  );
}
