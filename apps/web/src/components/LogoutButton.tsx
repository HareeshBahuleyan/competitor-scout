"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { apiMutate } from "@/lib/api";
import { meQueryOptions } from "@/lib/current-user";

type LogoutButtonProps = {
  compact?: boolean;
};

export function LogoutButton({ compact = false }: LogoutButtonProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const logout = useMutation({
    mutationFn: async () => {
      const me = await queryClient.fetchQuery(meQueryOptions);
      await apiMutate("/auth/logout", {
        csrfToken: me.csrf_token,
        method: "POST",
      });
    },
    onSuccess: () => {
      queryClient.clear();
      router.replace("/login");
    },
  });

  return (
    <div className={compact ? "" : "mt-4"}>
      <button
        aria-busy={logout.isPending}
        aria-label="Log out"
        className={
          compact
            ? "icon-button"
            : "flex min-h-10 w-full items-center gap-2 rounded-xl px-3 text-sm font-semibold text-slate-600 transition hover:bg-white hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
        }
        disabled={logout.isPending}
        onClick={() => logout.mutate()}
        title="Log out"
        type="button"
      >
        <svg
          aria-hidden="true"
          className="size-[18px] shrink-0"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.8"
          viewBox="0 0 24 24"
        >
          <path d="M10 5H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h4" />
          <path d="m14 8 4 4-4 4M8 12h10" />
        </svg>
        {compact ? null : <span>{logout.isPending ? "Logging out…" : "Log out"}</span>}
      </button>
      {logout.isError ? (
        <p className={compact ? "sr-only" : "mt-2 text-xs text-red-700"} role="alert">
          Could not log out. Try again.
        </p>
      ) : null}
    </div>
  );
}
