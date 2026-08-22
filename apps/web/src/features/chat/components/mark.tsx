import { cn } from "@/lib/utils";

export function NomercyMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      aria-hidden="true"
      className={cn("block", className)}
      fill="none"
    >
      <path
        d="M9 24V9l14 15V9"
        stroke="currentColor"
        strokeWidth="2.75"
        strokeLinecap="square"
        strokeLinejoin="miter"
      />
    </svg>
  );
}
