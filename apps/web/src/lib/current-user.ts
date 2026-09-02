import { queryOptions } from "@tanstack/react-query";

import { apiGetClient } from "@/lib/api";
import { meSchema } from "@/lib/schemas";

export const meQueryOptions = queryOptions({
  queryKey: ["me"],
  queryFn: () => apiGetClient("/api/v1/me", meSchema),
  staleTime: 60_000,
});
