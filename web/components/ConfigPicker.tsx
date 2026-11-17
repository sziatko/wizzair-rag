"use client";

import type { ReactNode } from "react";
import type { ConfigOption } from "@/lib/labels";

/** The setups as radio buttons, grouped by answer model; `right` fills the end of each row. */
export function ConfigPicker({
  options,
  value,
  onChange,
  legend,
  right,
}: {
  options: ConfigOption[];
  value: string;
  onChange: (id: string) => void;
  legend: string;
  right: (o: ConfigOption) => ReactNode;
}) {
  const models = [...new Set(options.map((o) => o.model))];
  return (
    <fieldset className="self-start md:sticky md:top-20">
      <legend className="mb-3 text-sm text-muted">{legend}</legend>
      <div className="flex flex-col gap-4">
        {models.map((model) => (
          <div key={model}>
            <p className="mb-1 px-3 text-sm font-semibold">{model}</p>
            {options
              .filter((o) => o.model === model)
              .map((o) => (
                <label
                  key={o.id}
                  className="flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-md px-3 text-sm hover:not-has-checked:bg-surface-muted has-checked:bg-accent-soft has-checked:font-medium has-checked:text-accent has-focus-visible:outline-2 has-focus-visible:outline-accent"
                >
                  <input type="radio" name="config" className="sr-only" checked={o.id === value} onChange={() => onChange(o.id)} />
                  <span>{o.retrieval}</span>
                  {right(o)}
                </label>
              ))}
          </div>
        ))}
      </div>
    </fieldset>
  );
}
