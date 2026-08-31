import { z } from "zod";

import {
  problemDetailsSchema,
  type ProblemDetails,
} from "@/lib/schemas";

export type JsonValue =
  | boolean
  | null
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export type MutationMethod = "DELETE" | "PATCH" | "POST" | "PUT";

type MutationOptions = {
  body?: JsonValue;
  csrfToken: string;
  method: MutationMethod;
};

type RequestOptions = {
  onUnauthorized?: () => void;
};

export class ApiError extends Error {
  readonly detail: string;
  readonly problem?: ProblemDetails;
  readonly status: number;

  constructor(status: number, detail: string, problem?: ProblemDetails) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.problem = problem;
  }
}

function assertSameOriginPath(path: string) {
  const sentinelOrigin = "https://same-origin.invalid";
  const resolved = new URL(path, sentinelOrigin);

  if (!path.startsWith("/") || resolved.origin !== sentinelOrigin) {
    throw new TypeError("API paths must be same-origin relative paths");
  }
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.toLowerCase().includes("application/problem+json")) {
    try {
      const parsed = problemDetailsSchema.safeParse(await response.json());
      if (parsed.success) {
        return new ApiError(response.status, parsed.data.detail, parsed.data);
      }
    } catch {
      // Fall through to the safe generic error below.
    }
  }

  const detail = response.status === 401 ? "authentication required" : `request failed: ${response.status}`;
  return new ApiError(response.status, detail);
}

async function request<Schema extends z.ZodTypeAny>(
  path: string,
  init: RequestInit,
  schema: Schema | undefined,
  options: RequestOptions = {},
): Promise<z.output<Schema> | undefined> {
  assertSameOriginPath(path);

  const response = await fetch(path, init);
  if (response.status === 401) {
    options.onUnauthorized?.();
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  if (response.status === 204) {
    return undefined;
  }
  if (!schema) {
    return undefined;
  }

  return schema.parse(await response.json());
}

const getRequestInit: RequestInit = {
  cache: "no-store",
  credentials: "include",
  headers: { Accept: "application/json" },
  method: "GET",
};

export async function apiGet<Schema extends z.ZodTypeAny>(path: string, schema: Schema): Promise<z.output<Schema>> {
  return (await request(path, getRequestInit, schema)) as z.output<Schema>;
}

function redirectToLogin() {
  if (typeof window !== "undefined") {
    // This framework-agnostic client helper runs outside React's router context.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  }
}

export async function apiGetClient<Schema extends z.ZodTypeAny>(path: string, schema: Schema): Promise<z.output<Schema>> {
  return (await request(path, getRequestInit, schema, {
    onUnauthorized: redirectToLogin,
  })) as z.output<Schema>;
}

export async function apiMutate<Schema extends z.ZodTypeAny>(
  path: string,
  options: MutationOptions,
  schema?: Schema,
): Promise<z.output<Schema> | undefined> {
  if (!options.csrfToken) {
    throw new TypeError("CSRF token is required for mutating requests");
  }

  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-CSRF-Token": options.csrfToken,
  };
  const init: RequestInit = {
    cache: "no-store",
    credentials: "include",
    headers,
    method: options.method,
  };

  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }

  return request(path, init, schema, { onUnauthorized: redirectToLogin });
}
