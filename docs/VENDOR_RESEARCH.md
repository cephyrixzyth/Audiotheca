# Vendor research pipeline (KVR + vi-control)

Local-first research for unknown library/plugin vendors. Does **not** auto-write
`vendor_db.py` — candidates stay in the harvest inbox until you approve them.

## Flow

1. **Gaps** — Vendor Tools → harvest gaps from a scan stamp (products with weak identity).
2. **SearXNG** — WEB-SPDR / Investigation lookup with presets:
   - `kvr` → `site:kvraudio.com …`
   - `vi-control` → `site:vi-control.net …`
3. **Harvest** — Vendor Tools presets **KVR Audio** / **vi-control** scrape seed forums into
   `vendor_harvest_candidates.json`.
4. **Approve** — Select candidates → **Add selected to vendor base** → `vendor_overrides.json`
   for the next scan.

API helper: `POST /api/vendors/research` returns the pipeline checklist + matching harvest
presets for a query.

## Presets

| UI harvest id | SearX preset | Sources |
|---------------|--------------|---------|
| `kvr` | `kvr` | kvraudio.com forums |
| `vi_control` | `vi-control` | vi-control.net community |
| `user_seeds` | `vendor` | mixed KVR/Reddit/SFX seeds |

Air-gap (`AUDIOTHECA_AIR_GAP=1`) disables outbound harvest/SearX; use CSV export/import offline.
