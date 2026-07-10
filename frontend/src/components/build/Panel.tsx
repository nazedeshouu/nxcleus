import type { ReactNode } from "react";
import type { Icon } from "@phosphor-icons/react";

export type PanelStatus = "default" | "pending" | "active" | "ok";

export function Panel({
  title,
  icon: IconCmp,
  status = "default",
  tag,
  children,
}: {
  title: string;
  icon: Icon;
  status?: PanelStatus;
  tag?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={`bv-panel ${status}`}>
      <header className="bv-panel-head">
        <IconCmp weight="regular" />
        <span className="bv-panel-title">{title}</span>
        {tag != null && <span className="bv-panel-tag">{tag}</span>}
      </header>
      <div className="bv-panel-body">{children}</div>
    </section>
  );
}
