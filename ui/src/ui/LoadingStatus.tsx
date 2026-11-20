import type { ReactNode } from "react";

export function LoadingStatus({ children = "Loading…" }: { children?: ReactNode }) {
  return <span className="loading-status" role="status"><i aria-hidden="true" />{children}</span>;
}
