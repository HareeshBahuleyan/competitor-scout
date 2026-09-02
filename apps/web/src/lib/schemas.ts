import { z } from "zod";

export const problemDetailsSchema = z.object({
  type: z.string().min(1),
  title: z.string().min(1),
  status: z.number().int().min(400).max(599),
  detail: z.string(),
  request_id: z.string().min(1),
});

export type ProblemDetails = z.infer<typeof problemDetailsSchema>;

export const meSchema = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
  display_name: z.string(),
  avatar_url: z.string().url().nullable(),
  timezone: z.string().min(1),
  csrf_token: z.string().min(1),
});

export type Me = z.infer<typeof meSchema>;

export function cursorPageSchema<ItemSchema extends z.ZodTypeAny>(itemSchema: ItemSchema) {
  return z.object({
    items: z.array(itemSchema),
    next_cursor: z.string().min(1).nullable(),
  });
}

export type CursorPage<Item> = {
  items: Item[];
  next_cursor: string | null;
};

export const competitorStatusSchema = z.enum(["discovering", "active", "paused", "deleted"]);

export const sourceCategorySchema = z.enum([
  "homepage",
  "pricing",
  "product",
  "features",
  "changelog",
  "documentation",
  "blog",
  "careers",
  "other",
]);

export const approvalStatusSchema = z.enum(["suggested", "approved", "rejected"]);

export const localTimeSchema = z
  .string()
  .regex(/^(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?$/);

export const timestampSchema = z.string().datetime({ offset: true });

export const competitorSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  primary_domain: z.string(),
  description: z.string(),
  status: competitorStatusSchema,
  daily_run_time_local: localTimeSchema,
  created_at: timestampSchema,
  updated_at: timestampSchema,
});

export type Competitor = z.infer<typeof competitorSchema>;

export const sourceSchema = z.object({
  id: z.string().uuid(),
  url: z.string().url(),
  source_category: sourceCategorySchema,
  title: z.string(),
  discovery_reason: z.string(),
  approval_status: approvalStatusSchema,
  created_at: timestampSchema,
  updated_at: timestampSchema,
});

export type Source = z.infer<typeof sourceSchema>;

export const competitorPageSchema = cursorPageSchema(competitorSchema);
export const sourcePageSchema = cursorPageSchema(sourceSchema);

const decimalNumberSchema = z
  .union([z.number(), z.string().regex(/^\d+(?:\.\d+)?$/)])
  .transform(Number)
  .refine(Number.isFinite);

const nullableMoneySchema = z.union([z.number(), z.string()]).transform(String).nullable();

export const findingCategorySchema = z.enum([
  "pricing",
  "product",
  "feature",
  "positioning",
  "integration",
  "customer_win",
  "partnership",
  "leadership",
  "hiring",
  "market_expansion",
  "other",
]);
export const significanceLevelSchema = z.enum(["low", "medium", "high", "critical"]);

export const findingSchema = z.object({
  id: z.string().uuid(),
  competitor_id: z.string().uuid(),
  originating_scout_run_id: z.string().uuid(),
  category: findingCategorySchema,
  title: z.string(),
  summary: z.string(),
  significance_explanation: z.string(),
  significance_level: significanceLevelSchema,
  confidence: decimalNumberSchema.pipe(z.number().min(0).max(1)),
  decision_rationale: z.string(),
  first_seen_at: timestampSchema,
  last_seen_at: timestampSchema,
  published_at: timestampSchema,
});
export type Finding = z.infer<typeof findingSchema>;
export const findingPageSchema = cursorPageSchema(findingSchema);

export const findingEvidenceSchema = z.object({
  id: z.string().uuid(),
  source_url: z
    .string()
    .url()
    .refine((value) => new URL(value).protocol === "https:", "HTTPS URL required"),
  source_domain: z.string(),
  source_title: z.string(),
  source_type: z.enum(["first_party", "news"]),
  published_at: timestampSchema.nullable(),
  captured_at: timestampSchema,
  quoted_text: z.string(),
  normalized_claim: z.string(),
  scout_run_id: z.string().uuid(),
  agent_task_id: z.string().uuid(),
  citation_order: z.number().int().positive(),
  is_primary: z.boolean(),
});
export type FindingEvidence = z.infer<typeof findingEvidenceSchema>;
export const findingEvidencePageSchema = cursorPageSchema(findingEvidenceSchema);

export const runTypeSchema = z.enum([
  "source_discovery",
  "daily_scout",
  "manual_scout",
  "weekly_brief",
]);
export const runStatusSchema = z.enum([
  "queued",
  "planning",
  "gathering",
  "synthesizing",
  "completed",
  "partial",
  "failed",
]);
export const runLifecycleStepSchema = z.object({
  state: runStatusSchema,
  occurred_at: timestampSchema,
});

export const runSchema = z.object({
  id: z.string().uuid(),
  competitor_id: z.string().uuid().nullable(),
  competitor_name: z.string().nullable(),
  finding_count: z.number().int().nonnegative(),
  run_type: runTypeSchema,
  status: runStatusSchema,
  scheduled_for: timestampSchema,
  started_at: timestampSchema.nullable(),
  completed_at: timestampSchema.nullable(),
  failure_code: z.string().nullable(),
  failure_summary: z.string().nullable(),
  partial_reasons: z.array(z.string()),
  input_tokens: z.number().int().nonnegative(),
  output_tokens: z.number().int().nonnegative(),
  tool_calls: z.number().int().nonnegative().nullable(),
  settled_cost_usd: nullableMoneySchema,
  created_at: timestampSchema,
  lifecycle: z.array(runLifecycleStepSchema).optional(),
});
export type Run = z.infer<typeof runSchema>;
export const runPageSchema = cursorPageSchema(runSchema);

export const agentTaskSchema = z.object({
  id: z.string().uuid(),
  scout_run_id: z.string().uuid(),
  parent_task_id: z.string().uuid().nullable(),
  role: z.enum(["main_planner", "child_researcher", "main_synthesizer"]),
  task_kind: z.string(),
  status: z.enum(["queued", "running", "succeeded", "failed", "cancelled"]),
  model: z.string(),
  objective: z.string(),
  source_scope: z.array(z.string()),
  attempt_count: z.number().int().nonnegative(),
  started_at: timestampSchema.nullable(),
  completed_at: timestampSchema.nullable(),
  input_tokens: z.number().int().nonnegative(),
  output_tokens: z.number().int().nonnegative(),
  tool_calls: z.number().int().nonnegative().nullable(),
  settled_cost_usd: nullableMoneySchema,
  validated_output: z.record(z.unknown()).nullable(),
  error_code: z.string().nullable(),
  error_summary: z.string().nullable(),
  created_at: timestampSchema,
});
export type AgentTask = z.infer<typeof agentTaskSchema>;
export const agentTaskPageSchema = cursorPageSchema(agentTaskSchema);

export const runUsageSchema = z.object({
  input_tokens: z.number().int().nonnegative().nullable().optional(),
  output_tokens: z.number().int().nonnegative().nullable().optional(),
  tool_calls: z.number().int().nonnegative().nullable().optional(),
  latency_ms: z.number().int().nonnegative().nullable().optional(),
  settled_cost_usd: nullableMoneySchema.optional(),
});

export const sourceDiscoveryResponseSchema = z.object({ run_id: z.string().uuid() });

export const startMonitoringResponseSchema = z.object({
  competitor: competitorSchema,
  run: runSchema.nullable(),
});

export const briefFindingReferenceSchema = z.object({
  finding_id: z.string().uuid(),
  statement: z.string().min(1).max(2_000),
});

export const briefSectionSchema = z.object({
  heading: z.string().min(1).max(200),
  narrative: z.string().min(1).max(5_000),
  references: z.array(briefFindingReferenceSchema).min(1).max(30),
});

export const EMPTY_BRIEF_TITLE = "Weekly brief: no material changes";
export const EMPTY_BRIEF_EXECUTIVE_SUMMARY =
  "No accepted material changes were published during this weekly period.";

export const weeklyBriefSchema = z
  .object({
    id: z.string().uuid(),
    scout_run_id: z.string().uuid(),
    period_start: z.string().date(),
    period_end: z.string().date(),
    title: z.string().min(1).max(300),
    executive_summary: z.string().min(1).max(5_000),
    sections: z.array(briefSectionSchema).max(20),
    published_at: timestampSchema,
    created_at: timestampSchema,
  })
  .superRefine((brief, context) => {
    if (
      brief.sections.length === 0 &&
      (brief.title !== EMPTY_BRIEF_TITLE ||
        brief.executive_summary !== EMPTY_BRIEF_EXECUTIVE_SUMMARY)
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Empty weekly briefs must use the canonical no-material-changes representation.",
        path: ["sections"],
      });
    }
  });

export type WeeklyBrief = z.infer<typeof weeklyBriefSchema>;
export const weeklyBriefPageSchema = cursorPageSchema(weeklyBriefSchema);

export const settingsSchema = z.object({
  display_name: z.string().min(1).max(200),
  timezone: z.string().min(1).max(64),
  default_daily_time: localTimeSchema,
  email_findings_enabled: z.boolean(),
  email_weekly_brief_enabled: z.boolean(),
  email_delivery_available: z.boolean(),
});

export type UserSettings = z.infer<typeof settingsSchema>;

export const usageSummaryRowSchema = z.object({
  date: z.string().date(),
  model: z.string().min(1),
  input_tokens: z.number().int().nonnegative(),
  output_tokens: z.number().int().nonnegative(),
  tool_calls: z.number().int().nonnegative().nullable(),
  settled_cost_usd: nullableMoneySchema,
});

export const usageSummarySchema = z.object({
  items: z.array(usageSummaryRowSchema),
});

export type UsageSummaryRow = z.infer<typeof usageSummaryRowSchema>;
