import type { ButtonHTMLAttributes, ReactNode } from "react";

type Kind = "primary" | "ghost" | "outline" | "danger";

const KIND: Record<Kind, string> = {
  primary: "border border-accent bg-accent text-white hover:bg-accent-ink",
  ghost: "border border-transparent bg-transparent text-ink hover:bg-surface-sunk",
  outline: "border border-line bg-surface text-ink hover:bg-surface-alt",
  danger: "border border-line bg-surface text-error hover:bg-error-soft",
};

export default function Button({
  kind = "ghost",
  size = "md",
  icon,
  children,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  kind?: Kind;
  size?: "sm" | "md";
  icon?: ReactNode;
}) {
  const pad = size === "sm" ? "px-2 py-1 text-[11.5px]" : "px-3 py-1.5 text-[12.5px]";
  return (
    <button
      {...rest}
      className={`inline-flex items-center gap-1.5 rounded-sm font-medium transition disabled:opacity-50 ${pad} ${KIND[kind]} ${className}`}
    >
      {icon}
      {children}
    </button>
  );
}
