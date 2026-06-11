import * as TooltipPrimitive from "@radix-ui/react-tooltip"
import type { FC } from "react"

import { cn } from "@/lib/utils"

export const TooltipProvider = TooltipPrimitive.Provider

export const Tooltip: FC<TooltipPrimitive.TooltipProps> = (props) => (
  <TooltipProvider>
    <TooltipPrimitive.Root {...props} />
  </TooltipProvider>
)

export const TooltipTrigger = TooltipPrimitive.Trigger

export const TooltipContent: FC<TooltipPrimitive.TooltipContentProps> = ({
  className,
  sideOffset = 4,
  ...props
}) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      sideOffset={sideOffset}
      className={cn(
        "z-50 overflow-hidden rounded-md border border-border bg-popover px-3 py-1.5 text-xs text-popover-foreground animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
        className,
      )}
      {...props}
    />
  </TooltipPrimitive.Portal>
)
