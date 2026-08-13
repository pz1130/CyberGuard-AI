import * as RT from "@radix-ui/react-tooltip";
import type { ReactElement, ReactNode } from "react";
import "./Tooltip.css";

export const TooltipProvider = RT.Provider;

export type TooltipProps = {
  content: ReactNode;
  children: ReactElement;
  side?: "top" | "right" | "bottom" | "left";
};

export function Tooltip({ content, children, side = "top" }: TooltipProps) {
  if (!content) return children;
  return (
    <RT.Root delayDuration={300}>
      <RT.Trigger asChild>{children}</RT.Trigger>
      <RT.Portal>
        <RT.Content className="ui-tooltip" side={side} sideOffset={6}>
          {content}
          <RT.Arrow className="ui-tooltip-arrow" />
        </RT.Content>
      </RT.Portal>
    </RT.Root>
  );
}
