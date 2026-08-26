import { forwardRef } from "react";
import type { ButtonHTMLAttributes } from "react";
import { Slot } from "@radix-ui/react-slot";
import { buttonClassName, type ButtonVariantProps } from "./buttonVariants";

export type { ButtonVariant, ButtonSize } from "./buttonVariants";

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    ButtonVariantProps {
  /** Render as the single child element (e.g. an <a> or router <Link>) via Radix Slot. */
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant, size, active, block, asChild, className, type, children, ...rest },
  ref,
) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      ref={ref}
      className={buttonClassName({ variant, size, active, block }, className)}
      // Slot forwards props to its child; only set a default button type for real buttons.
      type={asChild ? undefined : (type ?? "button")}
      {...rest}
    >
      {children}
    </Comp>
  );
});
