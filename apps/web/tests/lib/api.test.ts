import { z } from "zod";

import { ApiError, apiGet, apiGetClient, apiMutate } from "@/lib/api";

type StubResponseOptions = {
  body?: unknown;
  contentType?: string;
  status?: number;
};

function stubResponse({
  body,
  contentType = "application/json",
  status = 200,
}: StubResponseOptions = {}) {
  const json = vi.fn().mockResolvedValue(body);

  return {
    response: {
      headers: {
        get: (name: string) =>
          name.toLowerCase() === "content-type" ? contentType : null,
      },
      json,
      ok: status >= 200 && status < 300,
      status,
    } as unknown as Response,
    json,
  };
}

describe("apiGet", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses same-origin credentials and parses a successful response schema", async () => {
    const { response } = stubResponse({ body: { count: 3 } });
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiGet("/api/v1/summary", z.object({ count: z.number() }))).resolves.toEqual({
      count: 3,
    });
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/summary", {
      cache: "no-store",
      credentials: "include",
      headers: { Accept: "application/json" },
      method: "GET",
    });
  });

  it("surfaces RFC Problem Details from an error response", async () => {
    const problem = {
      type: "https://example.test/problems/validation",
      title: "Validation failed",
      status: 422,
      detail: "The request was invalid.",
      request_id: "req-123",
    };
    const { response } = stubResponse({
      body: problem,
      contentType: "application/problem+json; charset=utf-8",
      status: 422,
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    const error: unknown = await apiGet(
      "/api/v1/summary",
      z.object({ count: z.number() }),
    ).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toEqual(
      expect.objectContaining({
        detail: "The request was invalid.",
        name: "ApiError",
        problem,
        status: 422,
      }),
    );
  });

  it("does not access window when a server-safe request receives 401", async () => {
    const { response } = stubResponse({ status: 401 });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    const windowGetter = vi
      .spyOn(globalThis, "window", "get")
      .mockImplementation(() => {
        throw new Error("server execution must not access window");
      });

    await expect(
      apiGet("/api/v1/me", z.object({ id: z.string() })),
    ).rejects.toMatchObject({ status: 401 });
    expect(windowGetter).not.toHaveBeenCalled();
  });

  it("redirects a client request to login after a 401", async () => {
    const { response } = stubResponse({ status: 401 });
    const assign = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    vi.stubGlobal("window", { location: { assign } });

    await expect(
      apiGetClient("/api/v1/me", z.object({ id: z.string() })),
    ).rejects.toMatchObject({ status: 401 });
    expect(assign).toHaveBeenCalledOnce();
    expect(assign).toHaveBeenCalledWith("/login");
  });

  it("rejects an invalid successful response instead of trusting it", async () => {
    const { response } = stubResponse({ body: { count: "three" } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    await expect(
      apiGet("/api/v1/summary", z.object({ count: z.number() })),
    ).rejects.toBeInstanceOf(z.ZodError);
  });

  it("rejects absolute URLs before making a request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      apiGet("https://api.example.test/v1/me", z.object({ id: z.string() })),
    ).rejects.toThrow("API paths must be same-origin");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("apiMutate", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each(["POST", "PUT", "PATCH", "DELETE"] as const)(
    "sends %s JSON mutations with credentials and CSRF protection",
    async (method) => {
      const { response } = stubResponse({ body: { saved: true } });
      const fetchMock = vi.fn().mockResolvedValue(response);
      vi.stubGlobal("fetch", fetchMock);

      await expect(
        apiMutate(
          "/api/v1/settings",
          {
            body: { display_name: "Founder" },
            csrfToken: "csrf-token",
            method,
          },
          z.object({ saved: z.boolean() }),
        ),
      ).resolves.toEqual({ saved: true });
      expect(fetchMock).toHaveBeenCalledWith("/api/v1/settings", {
        body: JSON.stringify({ display_name: "Founder" }),
        cache: "no-store",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-token",
        },
        method,
      });
    },
  );

  it("returns undefined for 204 without attempting to parse a body", async () => {
    const { response, json } = stubResponse({ contentType: "", status: 204 });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    await expect(
      apiMutate("/auth/logout", { csrfToken: "csrf-token", method: "POST" }),
    ).resolves.toBeUndefined();
    expect(json).not.toHaveBeenCalled();
  });

  it("redirects to login when a mutation receives 401", async () => {
    const { response } = stubResponse({ status: 401 });
    const assign = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    vi.stubGlobal("window", { location: { assign } });

    await expect(
      apiMutate("/api/v1/settings", {
        body: { display_name: "Founder" },
        csrfToken: "csrf-token",
        method: "PATCH",
      }),
    ).rejects.toMatchObject({ status: 401 });
    expect(assign).toHaveBeenCalledWith("/login");
  });
});
