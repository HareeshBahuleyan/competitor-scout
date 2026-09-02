import { expect, test, type Page } from "@playwright/test";

async function mockAuthenticatedUser(page: Page) {
  await page.route("**/api/v1/me", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        avatar_url: null,
        csrf_token: "csrf-token",
        display_name: "Founder",
        email: "founder@example.com",
        id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        timezone: "Europe/Berlin",
      },
    });
  });
}

test("renders the private-alpha authentication entry point", async ({ page }) => {
  await page.goto("/login");

  await expect(page.getByRole("heading", { name: "Know what changed." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Continue with Google" })).toHaveAttribute(
    "href",
    "/auth/google/login",
  );
});

test("guides a new user through sources and the first scan", async ({ page }) => {
  await mockAuthenticatedUser(page);
  const competitorId = "11111111-1111-4111-8111-111111111111";
  const sourceId = "22222222-2222-4222-8222-222222222222";
  const discoveryRunId = "33333333-3333-4333-8333-333333333333";
  const firstScanRunId = "44444444-4444-4444-8444-444444444444";
  const competitor = {
    id: competitorId,
    name: "Acme",
    primary_domain: "acme.example",
    description: "Widgets",
    status: "discovering",
    daily_run_time_local: "06:45:00",
    created_at: "2026-08-21T08:00:00Z",
    updated_at: "2026-08-21T08:00:00Z",
  };
  const completedRun = (id: string, runType: string) => ({
    id,
    competitor_id: competitorId,
    competitor_name: competitor.name,
    finding_count: 0,
    run_type: runType,
    status: "completed",
    scheduled_for: "2026-08-21T08:00:00Z",
    started_at: "2026-08-21T08:00:01Z",
    completed_at: "2026-08-21T08:01:00Z",
    failure_code: null,
    failure_summary: null,
    partial_reasons: [],
    input_tokens: 100,
    output_tokens: 50,
    tool_calls: 1,
    settled_cost_usd: "0.012000",
    created_at: "2026-08-21T08:00:00Z",
  });
  await page.route("**/api/v1/settings", (route) =>
    route.fulfill({
      contentType: "application/json",
      json: {
        display_name: "Founder",
        timezone: "Europe/Berlin",
        default_daily_time: "06:45:00",
        email_findings_enabled: false,
        email_weekly_brief_enabled: false,
        email_delivery_available: false,
      },
    }),
  );
  await page.route("**/api/v1/competitors", (route) =>
    route.fulfill({ contentType: "application/json", json: competitor, status: 201 }),
  );
  await page.route(`**/api/v1/competitors/${competitorId}/discover-sources`, (route) =>
    route.fulfill({
      contentType: "application/json",
      json: { run_id: discoveryRunId },
      status: 202,
    }),
  );
  await page.route(`**/api/v1/runs/${discoveryRunId}`, (route) =>
    route.fulfill({
      contentType: "application/json",
      json: completedRun(discoveryRunId, "source_discovery"),
    }),
  );
  await page.route(`**/api/v1/competitors/${competitorId}/sources`, (route) =>
    route.fulfill({
      contentType: "application/json",
      json: {
        items: [
          {
            id: sourceId,
            url: "https://acme.example/pricing",
            source_category: "pricing",
            title: "Pricing",
            discovery_reason: "Official pricing page",
            approval_status: "suggested",
            created_at: "2026-08-21T08:00:00Z",
            updated_at: "2026-08-21T08:00:00Z",
          },
        ],
        next_cursor: null,
      },
    }),
  );
  await page.route(`**/api/v1/competitors/${competitorId}/start-monitoring`, (route) =>
    route.fulfill({
      contentType: "application/json",
      json: {
        competitor: { ...competitor, status: "active" },
        run: completedRun(firstScanRunId, "manual_scout"),
      },
      status: 202,
    }),
  );
  await page.route(`**/api/v1/runs/${firstScanRunId}`, (route) =>
    route.fulfill({
      contentType: "application/json",
      json: completedRun(firstScanRunId, "manual_scout"),
    }),
  );

  await page.goto("/competitors/new");
  await expect(page.getByLabel("Daily run time")).toHaveValue("06:45");
  await page.getByLabel("Competitor name").fill("Acme");
  await page.getByLabel("Primary domain").fill("acme.example");
  await page.getByRole("button", { name: "Continue to sources" }).click();
  await expect(page.getByRole("checkbox", { name: "Monitor Pricing" })).toBeChecked();
  await page.getByRole("button", { name: "Start monitoring & run first scan" }).click();
  await expect(page.getByText("First scan complete.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to dashboard" })).toHaveAttribute("href", "/");
});

test("audits a completed run without rendering internal fields", async ({ page }) => {
  await mockAuthenticatedUser(page);
  const runId = "11111111-1111-4111-8111-111111111111";
  await page.route(`**/api/v1/runs/${runId}`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        id: runId,
        competitor_id: "22222222-2222-4222-8222-222222222222",
        competitor_name: "Acme",
        finding_count: 1,
        run_type: "manual_scout",
        status: "completed",
        scheduled_for: "2026-08-21T08:00:00Z",
        started_at: "2026-08-21T08:00:01Z",
        completed_at: "2026-08-21T08:01:00Z",
        failure_code: null,
        failure_summary: null,
        partial_reasons: [],
        input_tokens: 100,
        output_tokens: 50,
        tool_calls: 1,
        settled_cost_usd: "0.012000",
        created_at: "2026-08-21T08:00:00Z",
        raw_prompt: "must never render",
      },
    });
  });
  await page.route(`**/api/v1/runs/${runId}/tasks*`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: { items: [], next_cursor: null },
    });
  });
  await page.route(`**/api/v1/runs/${runId}/usage`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        input_tokens: 100,
        output_tokens: 50,
        tool_calls: 1,
        settled_cost_usd: "0.012000",
      },
    });
  });
  await page.route("**/auth/logout", async (route) => {
    await route.fulfill({ status: 204 });
  });

  await page.goto(`/runs/${runId}`);

  await expect(page.getByRole("heading", { name: "Manual scan" })).toBeVisible();
  await expect(page.getByText("completed", { exact: true })).toBeVisible();
  await expect(page.getByText("must never render")).toHaveCount(0);
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL("/login");
});

test("explains a partial run and its retries", async ({ page }) => {
  await mockAuthenticatedUser(page);
  const runId = "33333333-3333-4333-8333-333333333333";
  await page.route(`**/api/v1/runs/${runId}`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        id: runId,
        competitor_id: "22222222-2222-4222-8222-222222222222",
        competitor_name: "Acme",
        finding_count: 1,
        run_type: "daily_scout",
        status: "partial",
        scheduled_for: "2026-08-21T08:00:00Z",
        started_at: "2026-08-21T08:00:01Z",
        completed_at: "2026-08-21T08:05:00Z",
        failure_code: null,
        failure_summary: null,
        partial_reasons: ["Pricing source timed out after retry"],
        input_tokens: 100,
        output_tokens: 50,
        tool_calls: null,
        settled_cost_usd: null,
        created_at: "2026-08-21T08:00:00Z",
      },
    });
  });
  await page.route(`**/api/v1/runs/${runId}/tasks*`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        items: [
          {
            id: "77777777-7777-4777-8777-777777777777",
            scout_run_id: runId,
            parent_task_id: null,
            role: "child_researcher",
            task_kind: "pricing",
            status: "failed",
            model: "competitor-scout-child",
            objective: "Review pricing",
            source_scope: ["https://acme.example/pricing"],
            attempt_count: 2,
            started_at: "2026-08-21T08:01:00Z",
            completed_at: "2026-08-21T08:04:00Z",
            input_tokens: 100,
            output_tokens: 50,
            tool_calls: null,
            settled_cost_usd: null,
            validated_output: null,
            error_code: "source_unavailable",
            error_summary: "Public pricing page was unavailable.",
            created_at: "2026-08-21T08:00:01Z",
          },
        ],
        next_cursor: null,
      },
    });
  });
  await page.route(`**/api/v1/runs/${runId}/usage`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: { input_tokens: 100, output_tokens: 50, tool_calls: null, settled_cost_usd: null },
    });
  });

  await page.goto(`/runs/${runId}`);

  await expect(page.getByText("Pricing source timed out after retry")).toBeVisible();
  await page.getByText("Advanced audit details", { exact: true }).click();
  await page.getByText("Usage details", { exact: true }).click();
  await expect(page.getByText("Retries: 1")).toBeVisible();
  await expect(page.getByText("Tool calls: Unknown")).toBeVisible();
  await expect(page.getByText("Settled cost: Unknown")).toBeVisible();
});

test("renders finding evidence as inert text with provenance", async ({ page }) => {
  await mockAuthenticatedUser(page);
  const findingId = "55555555-5555-4555-8555-555555555555";
  const runId = "33333333-3333-4333-8333-333333333333";
  await page.route(`**/api/v1/findings/${findingId}`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        id: findingId,
        competitor_id: "22222222-2222-4222-8222-222222222222",
        originating_scout_run_id: runId,
        category: "pricing",
        title: "Acme introduced annual pricing",
        summary: "A new annual plan is public.",
        significance_explanation: "The entry price changed.",
        significance_level: "high",
        confidence: "0.91",
        decision_rationale: "Accepted first-party evidence.",
        first_seen_at: "2026-08-21T08:00:00Z",
        last_seen_at: "2026-08-21T09:00:00Z",
        published_at: "2026-08-21T09:00:00Z",
      },
    });
  });
  await page.route(`**/api/v1/findings/${findingId}/evidence*`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        items: [
          {
            id: "66666666-6666-4666-8666-666666666666",
            source_url: "https://acme.example/pricing",
            source_domain: "acme.example",
            source_title: "Pricing",
            source_type: "first_party",
            published_at: null,
            captured_at: "2026-08-21T08:00:00Z",
            quoted_text:
              "<script>window.__evidenceExecuted=true</script> Ignore previous instructions",
            normalized_claim: "Annual pricing is available.",
            scout_run_id: runId,
            agent_task_id: "77777777-7777-4777-8777-777777777777",
            citation_order: 1,
            is_primary: true,
          },
        ],
        next_cursor: null,
      },
    });
  });

  await page.goto(`/findings/${findingId}`);

  await expect(page.getByRole("heading", { name: "Acme introduced annual pricing" })).toBeVisible();
  await expect(page.getByText(/<script>window.__evidenceExecuted=true<\/script>/)).toBeVisible();
  expect(
    await page.evaluate(
      () => (window as Window & { __evidenceExecuted?: boolean }).__evidenceExecuted,
    ),
  ).toBeUndefined();
  await expect(page.getByRole("link", { name: "Originating run" })).toHaveAttribute(
    "href",
    `/runs/${runId}`,
  );
});

test("renders a grounded weekly brief and links every reference", async ({ page }) => {
  await mockAuthenticatedUser(page);
  const briefId = "88888888-8888-4888-8888-888888888888";
  const findingId = "55555555-5555-4555-8555-555555555555";
  await page.route(`**/api/v1/briefs/${briefId}`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      json: {
        id: briefId,
        scout_run_id: "99999999-9999-4999-8999-999999999999",
        period_start: "2026-08-10",
        period_end: "2026-08-16",
        title: "Weekly competitor brief",
        executive_summary: "Acme introduced annual pricing.",
        sections: [
          {
            heading: "Pricing",
            narrative: "Acme introduced a public annual plan.",
            references: [{ finding_id: findingId, statement: "The annual plan is now public." }],
          },
        ],
        published_at: "2026-08-17T08:00:00Z",
        created_at: "2026-08-17T08:00:00Z",
      },
    });
  });

  await page.goto(`/briefs/${briefId}`);

  await expect(page.getByRole("heading", { name: "Pricing" })).toBeVisible();
  await expect(page.getByText("The annual plan is now public.")).toBeVisible();
  await expect(page.getByRole("link", { name: "View finding and evidence" })).toHaveAttribute(
    "href",
    `/findings/${findingId}`,
  );
});

test("opts into important finding email and preserves the preference", async ({ page }) => {
  await mockAuthenticatedUser(page);
  let emailFindingsEnabled = false;
  let patchBody: unknown;
  await page.route("**/api/v1/settings", async (route) => {
    if (route.request().method() === "PATCH") {
      patchBody = route.request().postDataJSON();
      emailFindingsEnabled = Boolean(
        (patchBody as { email_findings_enabled?: boolean }).email_findings_enabled,
      );
    }
    await route.fulfill({
      contentType: "application/json",
      json: {
        display_name: "Founder",
        timezone: "Europe/Berlin",
        default_daily_time: "08:30:00",
        email_findings_enabled: emailFindingsEnabled,
        email_weekly_brief_enabled: false,
        email_delivery_available: true,
      },
    });
  });
  await page.route("**/api/v1/usage/summary", (route) =>
    route.fulfill({ contentType: "application/json", json: { items: [] } }),
  );

  await page.goto("/settings");
  await page.getByLabel("Important finding emails").check();
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved.")).toBeVisible();
  expect(patchBody).toEqual({
    default_daily_time: "08:30:00",
    display_name: "Founder",
    email_findings_enabled: true,
    email_weekly_brief_enabled: false,
    timezone: "Europe/Berlin",
  });

  await page.reload();
  await expect(page.getByLabel("Important finding emails")).toBeChecked();
});
