import * as RS from "@radix-ui/react-select";
import "./Select.css";

export type SelectOption<T extends string> = { value: T; label: string };

export type SelectProps<T extends string> = {
  value: T;
  onChange: (v: T) => void;
  options: Array<SelectOption<T>>;
  ariaLabel: string;
  disabled?: boolean;
  size?: "sm" | "md";
};

export function Select<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
  disabled,
  size = "md",
}: SelectProps<T>) {
  return (
    <RS.Root
      value={value}
      onValueChange={(v) => onChange(v as T)}
      disabled={disabled}
    >
      <RS.Trigger
        className={`ui-select-trigger ui-select-trigger--${size}`}
        aria-label={ariaLabel}
      >
        <RS.Value />
        <RS.Icon className="ui-select-icon">▾</RS.Icon>
      </RS.Trigger>
      <RS.Portal>
        <RS.Content className="ui-select-content" position="popper" sideOffset={4}>
          <RS.Viewport>
            {options.map((o) => (
              <RS.Item key={o.value} value={o.value} className="ui-select-item">
                <RS.ItemText>{o.label}</RS.ItemText>
                <RS.ItemIndicator className="ui-select-check">✓</RS.ItemIndicator>
              </RS.Item>
            ))}
          </RS.Viewport>
        </RS.Content>
      </RS.Portal>
    </RS.Root>
  );
}
