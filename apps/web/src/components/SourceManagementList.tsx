"use client";

import { AlertDialog } from "@heroui/react";

import type { Source } from "@/lib/schemas";

type SourceDecision = "approved" | "rejected";

type SourceManagementListProps = {
  disabled?: boolean;
  onUpdate: (sourceId: string, decision: SourceDecision) => Promise<void> | void;
  pendingSourceId?: string | null;
  sources: Source[];
};

type SourceGroup = {
  description: string;
  id: string;
  sources: Source[];
  title: string;
};

const statusLabels = {
  approved: "Monitored",
  rejected: "Not monitored",
  suggested: "Awaiting review",
} as const;

const statusStyles = {
  approved: "bg-[var(--color-accent-soft)] text-[var(--color-accent-strong)]",
  rejected: "bg-slate-100 text-slate-600",
  suggested: "bg-amber-50 text-[var(--color-warning)]",
} as const;

export function SourceManagementList({
  disabled = false,
  onUpdate,
  pendingSourceId = null,
  sources,
}: SourceManagementListProps) {
  const monitored = sources.filter((source) => source.approval_status === "approved");
  const suggested = sources.filter((source) => source.approval_status === "suggested");
  const excluded = sources.filter((source) => source.approval_status === "rejected");

  const groups: SourceGroup[] = [
    {
      description:
        "Every scan fetches these pages. Removing the last monitored source pauses daily monitoring.",
      id: "monitored",
      sources: monitored,
      title: "Monitored sources",
    },
    {
      description: "Discovered or added but not yet part of scans.",
      id: "suggested",
      sources: suggested,
      title: "Awaiting review",
    },
    {
      description: "Excluded from scans. Add one back at any time.",
      id: "excluded",
      sources: excluded,
      title: "Not monitored",
    },
  ].filter((group) => group.sources.length > 0);

  return (
    <div className="space-y-6">
      {groups.map((group) => (
        <div className="space-y-3" key={group.id}>
          <div>
            <h3 className="eyebrow" id={`source-group-${group.id}`}>
              {group.title}
            </h3>
            <p className="mt-1 text-sm text-slate-600">{group.description}</p>
          </div>
          <ul aria-labelledby={`source-group-${group.id}`} className="space-y-3">
            {group.sources.map((source) => {
              const isPending = pendingSourceId === source.id;
              const actionsDisabled = disabled || isPending;
              const isMonitored = source.approval_status === "approved";

              return (
                <li className="surface p-4" key={source.id}>
                  <article className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="font-semibold text-slate-950">{source.title}</h4>
                        <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium capitalize text-slate-600">
                          {source.source_category}
                        </span>
                        <span
                          className={`rounded-full px-2 py-1 text-xs font-medium ${statusStyles[source.approval_status]}`}
                        >
                          {statusLabels[source.approval_status]}
                        </span>
                      </div>
                      <p className="mt-2 text-sm text-slate-600">{source.discovery_reason}</p>
                      <a
                        className="mt-2 block truncate text-sm font-medium text-blue-700 hover:underline"
                        href={source.url}
                        rel="noreferrer"
                        target="_blank"
                      >
                        {source.url}
                      </a>
                    </div>

                    <div className="flex shrink-0 gap-2">
                      {isMonitored ? (
                        monitored.length === 1 && !actionsDisabled ? (
                          <AlertDialog>
                            <AlertDialog.Trigger
                              aria-label={`Stop monitoring ${source.title}`}
                              className="inline-flex cursor-pointer items-center rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700"
                            >
                              Stop monitoring
                            </AlertDialog.Trigger>
                            <AlertDialog.Backdrop isKeyboardDismissDisabled={false}>
                              <AlertDialog.Container placement="center" size="md">
                                <AlertDialog.Dialog>
                                  <AlertDialog.Header>
                                    <AlertDialog.Icon status="warning" />
                                    <AlertDialog.Heading>
                                      Pause daily monitoring?
                                    </AlertDialog.Heading>
                                  </AlertDialog.Header>
                                  <AlertDialog.Body>
                                    Stopping monitoring for {source.title} leaves this competitor
                                    without a monitored source. Daily monitoring will pause until
                                    another source is monitored.
                                  </AlertDialog.Body>
                                  <AlertDialog.Footer>
                                    <AlertDialog.CloseTrigger>Keep source</AlertDialog.CloseTrigger>
                                    <button
                                      className="min-h-10 rounded-lg bg-[var(--color-danger)] px-4 py-2 font-medium text-white"
                                      onClick={() => void onUpdate(source.id, "rejected")}
                                      type="button"
                                    >
                                      Stop monitoring
                                    </button>
                                  </AlertDialog.Footer>
                                </AlertDialog.Dialog>
                              </AlertDialog.Container>
                            </AlertDialog.Backdrop>
                          </AlertDialog>
                        ) : (
                          <button
                            aria-label={`Stop monitoring ${source.title}`}
                            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 disabled:cursor-not-allowed disabled:text-slate-400"
                            disabled={actionsDisabled}
                            onClick={() => void onUpdate(source.id, "rejected")}
                            type="button"
                          >
                            Stop monitoring
                          </button>
                        )
                      ) : (
                        <button
                          aria-label={`Monitor ${source.title}`}
                          className="rounded-lg bg-slate-950 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                          disabled={actionsDisabled}
                          onClick={() => void onUpdate(source.id, "approved")}
                          type="button"
                        >
                          Monitor
                        </button>
                      )}
                      {source.approval_status === "suggested" ? (
                        <button
                          aria-label={`Dismiss ${source.title}`}
                          className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 disabled:cursor-not-allowed disabled:text-slate-400"
                          disabled={actionsDisabled}
                          onClick={() => void onUpdate(source.id, "rejected")}
                          type="button"
                        >
                          Dismiss
                        </button>
                      ) : null}
                    </div>
                  </article>
                  {isPending ? (
                    <p aria-live="polite" className="mt-3 text-sm text-slate-600">
                      Updating {source.title}…
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
