/* eslint-disable @next/next/no-img-element */
"use client";

import { useState } from "react";

export interface CompetitorFaviconProps {
  domain?: string | null;
  name: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const badgeSizes = {
  sm: "size-5 text-[10px] rounded-md",
  md: "size-7 text-xs rounded-lg",
  lg: "size-10 text-sm rounded-xl",
};

const imageSizes = {
  sm: "size-5 rounded-md",
  md: "size-7 rounded-lg",
  lg: "size-10 rounded-xl",
};

export function CompetitorFavicon({
  domain,
  name,
  size = "sm",
  className = "",
}: CompetitorFaviconProps) {
  const [hasError, setHasError] = useState(false);

  const cleanDomain = domain
    ? domain
        .trim()
        .toLowerCase()
        .replace(/^https?:\/\//i, "")
        .replace(/^www\./i, "")
        .split("/")[0]
        .split("?")[0]
    : "";

  const initial = name.trim().charAt(0).toUpperCase() || "?";

  if (!cleanDomain || hasError) {
    return (
      <span
        aria-hidden="true"
        className={`inline-flex shrink-0 items-center justify-center font-bold bg-slate-100 text-slate-700 border border-slate-200/80 ${badgeSizes[size]} ${className}`}
        data-testid="competitor-favicon-fallback"
      >
        {initial}
      </span>
    );
  }

  const faviconUrl = `https://www.google.com/s2/favicons?domain=${encodeURIComponent(cleanDomain)}&sz=64`;

  return (
    <img
      alt=""
      aria-hidden="true"
      className={`inline-block shrink-0 object-contain bg-white border border-slate-200/60 p-0.5 ${imageSizes[size]} ${className}`}
      data-testid="competitor-favicon-image"
      onError={() => setHasError(true)}
      src={faviconUrl}
    />
  );
}
