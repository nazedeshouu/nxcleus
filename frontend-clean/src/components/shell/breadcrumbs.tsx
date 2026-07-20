import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Crumb = { label: string; to?: string };

const Ctx = createContext<{ crumbs: Crumb[]; set: (c: Crumb[]) => void }>({ crumbs: [], set: () => {} });

export function BreadcrumbProvider({ children }: { children: ReactNode }) {
  const [crumbs, set] = useState<Crumb[]>([]);
  const value = useMemo(() => ({ crumbs, set }), [crumbs]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useCrumbs = () => useContext(Ctx).crumbs;

/** Detail pages call this to publish their trail into the shell top bar. */
export function useBreadcrumb(crumbs: Crumb[]) {
  const { set } = useContext(Ctx);
  const key = crumbs.map((c) => `${c.label}>${c.to ?? ""}`).join("|");
  useEffect(() => {
    set(crumbs);
    return () => set([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
}
