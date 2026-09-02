import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SelectField } from "@/components/ui/SelectField";

const options = [
  { label: "All categories", value: "" },
  { label: "Pricing", value: "pricing" },
  { label: "Product", value: "product" },
];

describe("SelectField", () => {
  it("uses the themed picker and submits its selected value through FormData", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(Object.fromEntries(new FormData(event.currentTarget)));
        }}
      >
        <SelectField id="category" label="Category" name="category" options={options} />
        <button type="submit">Apply filters</button>
      </form>,
    );

    const trigger = screen.getByRole("button", { name: /Category/ });
    expect(trigger).toHaveTextContent("All categories");

    await user.click(trigger);
    await user.click(screen.getByRole("option", { name: "Product" }));
    expect(trigger).toHaveTextContent("Product");

    await user.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(onSubmit).toHaveBeenCalledWith({ category: "product" });
  });

  it("shows and submits an existing filter value", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(new FormData(event.currentTarget).get("category"));
        }}
      >
        <SelectField
          defaultValue="pricing"
          id="category"
          label="Category"
          name="category"
          options={options}
        />
        <button type="submit">Apply filters</button>
      </form>,
    );

    expect(screen.getByRole("button", { name: /Category/ })).toHaveTextContent("Pricing");
    await user.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(onSubmit).toHaveBeenCalledWith("pricing");
  });
});
