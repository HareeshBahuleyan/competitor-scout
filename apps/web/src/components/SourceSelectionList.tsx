import type { Source } from "@/lib/schemas";

type SourceSelectionListProps = {
  disabled?: boolean;
  onToggle: (sourceId: string) => void;
  selectedSourceIds: Set<string>;
  sources: Source[];
};

export function SourceSelectionList({
  disabled = false,
  onToggle,
  selectedSourceIds,
  sources,
}: SourceSelectionListProps) {
  return (
    <ul className="space-y-3">
      {sources.map((source) => (
        <li className="surface p-4" key={source.id}>
          <label className="flex cursor-pointer items-start gap-3">
            <input
              aria-label={`Monitor ${source.title}`}
              checked={selectedSourceIds.has(source.id)}
              className="mt-1 size-4"
              disabled={disabled}
              onChange={() => onToggle(source.id)}
              type="checkbox"
            />
            <span className="min-w-0">
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-950">{source.title}</span>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium capitalize text-slate-600">
                  {source.source_category}
                </span>
              </span>
              <span className="mt-1 block text-sm text-slate-600">{source.discovery_reason}</span>
              <a
                className="mt-2 block truncate text-sm font-medium text-blue-700 hover:underline"
                href={source.url}
                onClick={(event) => event.stopPropagation()}
                rel="noreferrer"
                target="_blank"
              >
                {source.url}
              </a>
            </span>
          </label>
        </li>
      ))}
    </ul>
  );
}
