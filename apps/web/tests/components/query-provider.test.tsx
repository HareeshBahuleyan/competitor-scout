import { render, screen } from "@testing-library/react";
import { useQueryClient } from "@tanstack/react-query";

import { QueryProvider } from "@/lib/query";

function QueryConsumer() {
  const client = useQueryClient();

  return <p>{client ? "Query client ready" : "Query client missing"}</p>;
}

describe("QueryProvider", () => {
  it("provides one query client to its descendants", () => {
    render(
      <QueryProvider>
        <QueryConsumer />
      </QueryProvider>,
    );

    expect(screen.getByText("Query client ready")).toBeVisible();
  });
});
