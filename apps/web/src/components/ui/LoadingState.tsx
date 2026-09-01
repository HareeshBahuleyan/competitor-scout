import { Skeleton } from "@heroui/react";

type LoadingStateProps = {
  label: string;
  rows?: number;
};

export function LoadingState({ label, rows = 3 }: LoadingStateProps) {
  return (
    <div aria-label={label} className="space-y-3" role="status">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton className="h-20 rounded-[var(--radius-card)]" key={index} />
      ))}
    </div>
  );
}
