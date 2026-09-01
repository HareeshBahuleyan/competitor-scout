import { z } from "zod";

import {
  agentTaskSchema,
  competitorPageSchema,
  competitorSchema,
  cursorPageSchema,
  findingEvidenceSchema,
  findingSchema,
  meSchema,
  problemDetailsSchema,
  settingsSchema,
  usageSummarySchema,
  weeklyBriefSchema,
  runSchema,
  sourcePageSchema,
  sourceSchema,
} from "@/lib/schemas";

describe("foundational API schemas", () => {
  it("parses RFC Problem Details returned by the API", () => {
    expect(
      problemDetailsSchema.parse({
        type: "about:blank",
        title: "Not found",
        status: 404,
        detail: "The resource was not found.",
        request_id: "req-123",
      }),
    ).toEqual({
      type: "about:blank",
      title: "Not found",
      status: 404,
      detail: "The resource was not found.",
      request_id: "req-123",
    });
  });

  it("requires the authenticated user response to include a CSRF token", () => {
    const authenticatedUser = {
      id: "8b4f03f8-2db9-4f7d-8c5e-3351846b842c",
      email: "founder@example.com",
      display_name: "Founder",
      avatar_url: null,
      timezone: "Europe/Berlin",
      csrf_token: "signed-csrf-token",
    };

    expect(meSchema.parse(authenticatedUser)).toEqual(authenticatedUser);
    expect(() => meSchema.parse({ ...authenticatedUser, csrf_token: undefined })).toThrow(
      z.ZodError,
    );
  });

  it("builds typed cursor-page envelopes from an item schema", () => {
    const pageSchema = cursorPageSchema(z.object({ id: z.string().uuid() }));
    const page = {
      items: [{ id: "8b4f03f8-2db9-4f7d-8c5e-3351846b842c" }],
      next_cursor: "cursor-2",
    };

    expect(pageSchema.parse(page)).toEqual(page);
    expect(pageSchema.parse({ items: [], next_cursor: null })).toEqual({
      items: [],
      next_cursor: null,
    });
  });

  it("parses the complete competitor read contract", () => {
    const competitor = {
      id: "8b4f03f8-2db9-4f7d-8c5e-3351846b842c",
      name: "Acme Analytics",
      primary_domain: "acme.example",
      description: "Product analytics platform.",
      status: "active",
      daily_run_time_local: "08:30:00",
      created_at: "2026-08-21T08:00:00Z",
      updated_at: "2026-08-21T08:05:00+00:00",
    };

    expect(competitorSchema.parse(competitor)).toEqual(competitor);
    expect(competitorPageSchema.parse({ items: [competitor], next_cursor: null })).toEqual({
      items: [competitor],
      next_cursor: null,
    });
    expect(() => competitorSchema.parse({ ...competitor, status: "unknown" })).toThrow(z.ZodError);
    expect(() => competitorSchema.parse({ ...competitor, daily_run_time_local: "8:30" })).toThrow(
      z.ZodError,
    );
  });

  it("parses the complete monitored-source read contract", () => {
    const source = {
      id: "de26990b-c5d5-48ab-bce7-e4d63d7fa94f",
      url: "https://acme.example/changelog",
      source_category: "changelog",
      title: "Changelog",
      discovery_reason: "Tracks product releases.",
      approval_status: "suggested",
      created_at: "2026-08-21T08:00:00Z",
      updated_at: "2026-08-21T08:05:00+00:00",
    };

    expect(sourceSchema.parse(source)).toEqual(source);
    expect(sourcePageSchema.parse({ items: [source], next_cursor: "cursor-2" })).toEqual({
      items: [source],
      next_cursor: "cursor-2",
    });
    expect(() => sourceSchema.parse({ ...source, source_category: "social" })).toThrow(z.ZodError);
    expect(() => sourceSchema.parse({ ...source, created_at: "yesterday" })).toThrow(z.ZodError);
  });
});

describe("audit schemas", () => {
  it("parses finding decimals and strips unknown model fields", () => {
    const parsed = findingSchema.parse({
      id: "55555555-5555-4555-8555-555555555555",
      competitor_id: "11111111-1111-4111-8111-111111111111",
      originating_scout_run_id: "44444444-4444-4444-8444-444444444444",
      category: "pricing",
      title: "Pricing changed",
      summary: "Summary",
      significance_explanation: "Explanation",
      significance_level: "high",
      confidence: "0.91",
      decision_rationale: "Rationale",
      first_seen_at: "2026-08-21T08:00:00Z",
      last_seen_at: "2026-08-21T09:00:00Z",
      published_at: "2026-08-21T09:00:00Z",
      prompt: "must be stripped",
    });
    expect(parsed.confidence).toBe(0.91);
    expect(parsed).not.toHaveProperty("prompt");
  });

  it("rejects unsafe evidence URLs and strips task secrets", () => {
    expect(() =>
      findingEvidenceSchema.parse({
        id: "66666666-6666-4666-8666-666666666666",
        source_url: "javascript:alert(1)",
        source_domain: "example.com",
        source_title: "Source",
        source_type: "first_party",
        published_at: null,
        captured_at: "2026-08-21T08:00:00Z",
        quoted_text: "Quote",
        normalized_claim: "Claim",
        scout_run_id: "44444444-4444-4444-8444-444444444444",
        agent_task_id: "77777777-7777-4777-8777-777777777777",
        citation_order: 1,
        is_primary: true,
      }),
    ).toThrow();
    const task = agentTaskSchema.parse({
      id: "77777777-7777-4777-8777-777777777777",
      scout_run_id: "44444444-4444-4444-8444-444444444444",
      parent_task_id: null,
      role: "child_researcher",
      task_kind: "pricing",
      status: "succeeded",
      model: "research",
      objective: "Review pricing",
      source_scope: ["https://example.com"],
      attempt_count: 1,
      started_at: null,
      completed_at: null,
      input_tokens: 0,
      output_tokens: 0,
      tool_calls: null,
      settled_cost_usd: null,
      validated_output: null,
      error_code: null,
      error_summary: null,
      created_at: "2026-08-21T08:00:00Z",
      prompt: "secret",
      raw_response: "secret",
    });
    expect(task).not.toHaveProperty("prompt");
    expect(task).not.toHaveProperty("raw_response");
  });

  it("validates run lifecycle enums", () => {
    const base = {
      id: "44444444-4444-4444-8444-444444444444",
      competitor_id: null,
      run_type: "daily_scout",
      scheduled_for: "2026-08-21T08:00:00Z",
      started_at: null,
      completed_at: null,
      failure_code: null,
      failure_summary: null,
      partial_reasons: [],
      input_tokens: 0,
      output_tokens: 0,
      tool_calls: null,
      settled_cost_usd: null,
      created_at: "2026-08-21T08:00:00Z",
    };
    expect(() => runSchema.parse({ ...base, status: "invented" })).toThrow();
    expect(runSchema.parse({ ...base, status: "queued" }).status).toBe("queued");
  });
});

describe("brief, settings, and aggregate usage schemas", () => {
  it("validates grounded and deterministic empty weekly briefs", () => {
    const base = {
      id: "88888888-8888-4888-8888-888888888888",
      scout_run_id: "44444444-4444-4444-8444-444444444444",
      period_start: "2026-08-10",
      period_end: "2026-08-16",
      published_at: "2026-08-17T08:00:00Z",
      created_at: "2026-08-17T08:00:00Z",
    };
    const grounded = weeklyBriefSchema.parse({
      ...base,
      title: "Weekly competitor brief",
      executive_summary: "A meaningful change was accepted.",
      sections: [
        {
          heading: "Pricing",
          narrative: "Acme introduced a new annual tier.",
          references: [
            {
              finding_id: "55555555-5555-4555-8555-555555555555",
              statement: "Acme introduced a new annual tier.",
            },
          ],
        },
      ],
      prompt: "must be stripped",
    });
    expect(grounded.sections[0]?.references).toHaveLength(1);
    expect(grounded).not.toHaveProperty("prompt");

    expect(
      weeklyBriefSchema.parse({
        ...base,
        title: "Weekly brief: no material changes",
        executive_summary: "No accepted material changes were published during this weekly period.",
        sections: [],
      }).sections,
    ).toEqual([]);
    expect(() =>
      weeklyBriefSchema.parse({
        ...base,
        title: "Nothing happened",
        executive_summary: "Trust me.",
        sections: [],
      }),
    ).toThrow(z.ZodError);
  });

  it("accepts only public settings and preserves unknown usage totals", () => {
    expect(
      settingsSchema.parse({
        display_name: "Founder",
        timezone: "Europe/Berlin",
        default_daily_time: "08:30:00",
        main_model: "must-not-reach-the-view",
      }),
    ).toEqual({
      display_name: "Founder",
      timezone: "Europe/Berlin",
      default_daily_time: "08:30:00",
    });
    expect(() =>
      settingsSchema.parse({
        display_name: "Founder",
        timezone: "Europe/Berlin",
        default_daily_time: "8:30",
      }),
    ).toThrow(z.ZodError);

    expect(
      usageSummarySchema.parse({
        items: [
          {
            date: "2026-08-21",
            model: "competitor-scout-main",
            input_tokens: 100,
            output_tokens: 20,
            tool_calls: null,
            settled_cost_usd: null,
          },
        ],
      }).items[0],
    ).toMatchObject({ tool_calls: null, settled_cost_usd: null });
  });
});
