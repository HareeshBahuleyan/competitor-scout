/** Display helpers for the scan (run) contract. */

function humanizeCode(value: string) {
  const words = value.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Reader-facing text for why a scan finished partial.
 *
 * The backend owns this vocabulary and sends a sentence for every code it has
 * copy for, so a code without one is a new backend reason rather than a missing
 * translation here. Those fall back to the humanized code so the reason still
 * reaches the reader instead of disappearing.
 */
export function partialReasonLabels(
  reasons: readonly string[],
  summaries: readonly string[],
): string[] {
  return summaries.length > 0 ? [...summaries] : reasons.map(humanizeCode);
}
