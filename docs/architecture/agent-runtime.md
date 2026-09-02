# Scout agent runtime

The Scout runtime turns an approved competitor scope into bounded, evidence-backed findings. It separates planning, research, validation, synthesis, and publication so untrusted model output never writes directly to the product record.

## Daily and manual Scout Runs

```mermaid
stateDiagram-v2
    [*] --> queued
    queued --> planning
    planning --> gathering: valid bounded plan
    gathering --> synthesizing: accepted evidence
    synthesizing --> completed: grounded publication
    gathering --> partial: usable evidence and bounded failure
    synthesizing --> partial: usable output and bounded failure
    planning --> failed: invalid or unavailable plan
    gathering --> failed: no valid evidence
    synthesizing --> failed: invalid synthesis or publication failure
    completed --> [*]
    partial --> [*]
    failed --> [*]
```

1. The API or scheduler creates a `ScoutRun` and durable job.
2. `ScoutOrchestrator` locks and starts the queued run, loads the competitor, approved URLs, recent findings, and prior context.
3. The main model returns a structured `ScoutPlan` whose task count, search calls, and first-party source scope are validated.
4. Child tasks execute in bounded waves. Each task has a role, kind, model, objective, scope, attempts, timestamps, usage, and safe failure data.
5. Evidence is normalized, checked against approved or permitted source scope, deduplicated, and persisted.
6. The main model synthesizes accepted evidence into a structured result.
7. `FindingPublicationService` revalidates grounding, confidence, citations, and deduplication before publishing findings.
8. The run ends as `completed`, `partial`, or `failed`, with usage and safe reasons recorded.

Re-entry into an intermediate run state indicates recovery after lease loss. The runtime terminalizes interrupted ownership rather than blindly duplicating work.

## Other run types

- **Source discovery** searches within configured limits, validates public URLs and registrable-domain scope, and creates suggestions without overriding prior approval decisions.
- **Weekly brief** is scheduled only when the completed user-local week contains at least one daily or manual Scout Run. It selects accepted findings from that period, asks the provider for a structured grounded summary, and persists finding references. Source discovery alone does not schedule a brief because it cannot publish findings. When qualifying Scout Runs produced no accepted findings, a canonical empty brief represents no material changes.

The brief title and executive summary are the only model-authored strings the interface shows verbatim, so the synthesis prompt constrains the title to state what changed rather than name the document type. The canonical empty title is a persisted value shared by `apps/backend/src/competitor_scout/schemas/briefs.py` and `apps/web/src/lib/schemas.ts`, and both reject a section-less brief that does not use it. Changing it requires updating both constants and migrating stored rows in the same change; migration `0008_rename_empty_brief_title` is the precedent.

## Trust and grounding

Prompts mark fetched content as untrusted and prohibit source instructions from changing the Scout objective. Structured provider output is necessary but not sufficient: application code validates plan limits, URLs, evidence scope, quoted material, normalized claims, confidence, citations, and publication ownership.

Approved first-party URLs define the core monitoring boundary. News evidence is subject to its own type and URL checks. Direct quoted evidence and source metadata remain attached to published findings for auditability.

## Budgets and concurrency

Every provider interaction is constrained by configured model, token, deadline, repair, retry, search-call, run-cost, user-daily-cost, and concurrency limits. Usage records distinguish known settled values from unavailable provider metadata; unknown values must not be silently treated as zero.

A task's search budget and the gateway's loop bound are related but not the same number. `MAX_CHILD_SEARCH_CALLS` and `MAX_SOURCE_DISCOVERY_SEARCH_CALLS` cap the searches a task may make, and the task prompt carries that cap. `max_tool_iterations` bounds every turn of Otari's model/tool loop, so a wasted search, an intermediate reasoning turn, and the turn that emits the structured result each spend one. Exceeding it is rejected as `otari_tool_iteration_limit`, which discards the whole call rather than returning partial work, so `tool_iteration_budget` in `agents/orchestrator.py` sizes the loop at the search budget plus `TOOL_ITERATION_HEADROOM`, clamped to the gateway's ceiling of 25. The headroom must stay above zero: sizing the loop at exactly the search budget plus one makes any imperfect model turn fail the task. Because Otari reports no tool-call count, the prompt and this loop bound are the only enforcement of the search budget.

Settled cost has two sources. Otari attaches `cost_usd` and `pricing_source` to a completion only when its platform settles inside the gateway's inline budget. When the completion carries no cost, `OtariClient` looks the amount up from Otari's durable `GET /api/v1/request-costs/{request_id}` endpoint, using the `X-Otari-Request-ID` header of the completion and retrying the `202` pending answer within `OTARI_COST_LOOKUP_ATTEMPTS` and `OTARI_COST_LOOKUP_DELAY_SECONDS`. A settlement counts only when it reports usage and names a pricing source, so an unpriced model stays unknown instead of reading as a free call, and a failed or still-pending lookup leaves the cost unknown rather than blocking the run. Otari reports no tool-call count on either path, so that metric is not part of usage reporting.

The `ScoutOrchestrator` owns an in-process semaphore shared by handlers in one worker process. Production therefore runs exactly one worker replica. Horizontal scaling requires a database-backed or external global permit before changing this invariant.

Cost or child-task failures can produce `partial` only when usable validated evidence or output remains. No valid evidence is a failure, not an empty successful run.

## Changing the runtime

When changing prompts, contracts, orchestration, or publication:

1. Update structured contracts and prompts together.
2. Preserve explicit scope, trust, and cost validation outside the model.
3. Add unit tests for limit, repair, retry, state, usage, and failure behavior.
4. Update recorded contract fixtures if the provider protocol intentionally changes.
5. Extend deterministic evals for signal quality, grounding, or prompt injection.
6. Keep normal verification offline. Run the hosted evaluation only with explicit approval, `ALLOW_PAID_OTARI_EVALS=true`, and `--confirm-paid-run`.
