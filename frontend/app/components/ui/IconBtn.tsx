import type { ButtonHTMLAttributes, ReactNode } from "react";

export default function IconBtn({
  active,
  children,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean; children: ReactNode }) {
  return (
    <button
      {...rest}
      className={`inline-flex h-[26px] w-[26px] items-center justify-center rounded-sm border text-ink ${
        active ? "border-line-soft bg-surface-sunk" : "border-transparent"
      } ${className}`}
    >
      {children}
    </button>
  );
}
