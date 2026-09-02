"use client";

import { useRef, useState } from "react";

import type { Source } from "@/lib/schemas";

type SourceDecision = "approved" | "rejected";

type SourceApprovalListProps = {
  disabled?: boolean;
  onUpdate: (sourceId: string, decision: SourceDecision) => Promise<void> | void;
  pendingSourceId?: string | null;
  sources: Source[];
};

export function SourceApprovalList({
  disabled = false,
  onUpdate,
  pendingSourceId = null,
  sources,
}: SourceApprovalListProps) {
  const hasApprovedSource = sources.some((source) => source.approval_status === "approved");
  const approvedCount = sources.filter((source) => source.approval_status === "approved").length;
  const [confirmSource, setConfirmSource] = useState<Source | null>(null);
  const rejectButtons = useRef(new Map<string, HTMLButtonElement>());

  function closeConfirmation() {
    const sourceId = confirmSource?.id;
    setConfirmSource(null);
    if (sourceId) requestAnimationFrame(() => rejectButtons.current.get(sourceId)?.focus());
  }

  function reject(source: Source) {
    if (source.approval_status === "approved" && approvedCount === 1) {
      setConfirmSource(source);
      return;
    }
    void onUpdate(source.id, "rejected");
  }

  return (
    <section aria-labelledby="source-approvals-heading" className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold" id="source-approvals-heading">
          Suggested sources
        </h2>
        <p className="mt-1 text-sm text-slate-600" role="status">
          {hasApprovedSource
            ? "At least one trusted source is approved."
            : "Approve at least one trusted source before activating monitoring."}
        </p>
      </div>

      <ul className="space-y-3">
        {sources.map((source) => {
          const isPending = pendingSourceId === source.id;
          const actionsDisabled = disabled || isPending;

          return (
            <li className="surface p-4" key={source.id}>
              <article className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold text-slate-950">{source.title}</h3>
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium capitalize text-slate-600">
                      {source.source_category}
                    </span>
                    <span className="rounded-full bg-blue-50 px-2 py-1 text-xs font-medium capitalize text-blue-700">
                      {source.approval_status}
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
                  <button
                    aria-label={`Approve ${source.title}`}
                    className="rounded-lg bg-slate-950 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                    disabled={actionsDisabled}
                    onClick={() => void onUpdate(source.id, "approved")}
                    type="button"
                  >
                    Approve
                  </button>
                  <button
                    aria-label={`Reject ${source.title}`}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 disabled:cursor-not-allowed disabled:text-slate-400"
                    disabled={actionsDisabled}
                    onClick={() => reject(source)}
                    ref={(node) => {
                      if (node) rejectButtons.current.set(source.id, node);
                      else rejectButtons.current.delete(source.id);
                    }}
                    type="button"
                  >
                    Reject
                  </button>
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
      {confirmSource ? (
        <div
          aria-labelledby="reject-source-heading"
          aria-modal="true"
          className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 p-4"
          role="dialog"
        >
          <div className="surface max-w-md space-y-4 p-6">
            <h2 className="text-xl font-semibold" id="reject-source-heading">
              Stop scheduled monitoring?
            </h2>
            <p className="text-sm text-slate-600">
              Rejecting {confirmSource.title} leaves this monitor without an approved source, so
              scheduled monitoring will stop until another source is approved.
            </p>
            <div className="flex justify-end gap-2">
              <button
                autoFocus
                className="rounded-lg border border-slate-300 px-4 py-2 font-medium"
                onClick={closeConfirmation}
                type="button"
              >
                Keep source
              </button>
              <button
                className="rounded-lg bg-red-700 px-4 py-2 font-medium text-white"
                onClick={() => {
                  void onUpdate(confirmSource.id, "rejected");
                  setConfirmSource(null);
                }}
                type="button"
              >
                Reject source
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
