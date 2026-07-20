import type { ReactNode } from "react";
import { useReveal } from "../../lib/useReveal";

/** Wraps children with a scroll-in reveal (motivated: section entrance hierarchy). */
export function Reveal({ children, className = "", as = "div" }: { children: ReactNode; className?: string; as?: "div" | "section" }) {
  const ref = useReveal<HTMLDivElement>();
  const Tag = as as "div";
  return (
    <Tag ref={ref} className={`reveal ${className}`}>
      {children}
    </Tag>
  );
}
