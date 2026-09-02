"use client";

import { Label, ListBox, ListBoxItem, Select } from "@heroui/react";
import { useState } from "react";

const EMPTY_VALUE_KEY = "__competitor_scout_empty_select_value__";

export type SelectFieldOption = {
  label: string;
  value: string;
};

type SelectFieldProps = {
  defaultValue?: string;
  id: string;
  isDisabled?: boolean;
  label: string;
  name: string;
  options: readonly SelectFieldOption[];
};

/**
 * Product-styled single select that preserves native GET/POST form submission.
 * HeroUI owns the visible, accessible picker while the hidden input carries the
 * selected value into FormData.
 */
export function SelectField({
  defaultValue = "",
  id,
  isDisabled = false,
  label,
  name,
  options,
}: SelectFieldProps) {
  const [selectedValue, setSelectedValue] = useState(defaultValue);
  const selectedKey = selectedValue || EMPTY_VALUE_KEY;

  return (
    <div className="space-y-1">
      <input name={name} type="hidden" value={selectedValue} />
      <Select
        className="w-full"
        id={id}
        isDisabled={isDisabled}
        onSelectionChange={(key) => {
          const nextValue = String(key);
          setSelectedValue(nextValue === EMPTY_VALUE_KEY ? "" : nextValue);
        }}
        selectedKey={selectedKey}
      >
        <Label className="field-label">{label}</Label>
        <Select.Trigger className="w-full justify-between">
          <Select.Value />
          <Select.Indicator />
        </Select.Trigger>
        <Select.Popover className="max-h-80">
          <ListBox>
            {options.map((option) => (
              <ListBoxItem
                id={option.value || EMPTY_VALUE_KEY}
                key={option.value || EMPTY_VALUE_KEY}
                textValue={option.label}
              >
                {option.label}
              </ListBoxItem>
            ))}
          </ListBox>
        </Select.Popover>
      </Select>
    </div>
  );
}
