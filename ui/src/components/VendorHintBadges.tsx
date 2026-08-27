import { useEffect, useState } from "react";
import { fetchVendorHints } from "../api/client";
import { Badge } from "../ui";

type Props = {
  path: string;
  name?: string;
};

/** BTQ-FPT + SFX-MAP vendor hint badges for investigation rows. */
export function VendorHintBadges({ path, name }: Props) {
  const [boutique, setBoutique] = useState<string[]>([]);
  const [sfx, setSfx] = useState<string[]>([]);

  useEffect(() => {
    if (!path) return;
    void fetchVendorHints(path)
      .then((res) => {
        const b = res.boutique as { matches?: string[] } | undefined;
        const s = res.sfx_map as { vendor_hints?: string[] } | undefined;
        setBoutique(b?.matches ?? []);
        setSfx(s?.vendor_hints ?? []);
      })
      .catch(() => {
        setBoutique([]);
        setSfx([]);
      });
  }, [path, name]);

  if (!boutique.length && !sfx.length) return null;

  return (
    <span className="vendor-hint-badges">
      {boutique.map((tag) => (
        <Badge key={`b-${tag}`} tone="ready" title="BTQ-FPT boutique match">
          {tag}
        </Badge>
      ))}
      {sfx.slice(0, 2).map((tag) => (
        <Badge key={`s-${tag}`} tone="accent" title="SFX-MAP BWF library hint">
          {tag}
        </Badge>
      ))}
    </span>
  );
}
