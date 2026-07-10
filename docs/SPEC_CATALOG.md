# Audiotheca — Architecture Spec Catalog

Engine **10.0.0** · Web UI / API **1.0.12**

The spec catalog tracks **94 feature codes** across five sections. As of 1.0.12, all codes are **`done`** — each has a module, invoke handler (backend) or UI surface (UI-LOG), and pytest coverage.

## Sections

| Section | Count | Focus |
|---------|-------|--------|
| **SYS-ING** | 16 | Environment isolation, telemetry, path masking, mount watcher, virtual paths, drive cooldown |
| **AUD-PIP** | 25 | BWF metadata, multitrack collapse, acoustic dedupe, waveform cache, installer harvest, LUFS/BPM/key |
| **AI-SEC** | 14 | MCP lookup, web spider, tag generation, malware quarantine/shred, execution interceptor |
| **LFC-ORCH** | 18 | Version verify, cloud cache, S3 connector, path relocation, transfer bundle, DAW sidecar blueprint |
| **UI-LOG** | 21 | Canvas layout, audio preview, tempo sync, log filters, theme studio, layout presets |

## API

```bash
# Summary counts
curl -s http://127.0.0.1:8787/api/spec/catalog | jq .

# Single code metadata
curl -s http://127.0.0.1:8787/api/spec/NET-SAFE | jq .

# Invoke handler (backend codes only)
curl -s -X POST http://127.0.0.1:8787/api/spec/NET-SAFE/invoke \
  -H "Content-Type: application/json" -d '{}' | jq .
```

Registry source: `audiotheca/spec/schema.py` · Handlers: `audiotheca/spec/handlers.py`

## UI surfaces

| Tab / panel | Spec codes (examples) |
|-------------|---------------------|
| **Environment** | ISO-ENV, MNT-LSTN, TLM-PERF, SYM-AGG, CLD-CACHE, S3-CONN, Orchestration tools |
| **Security** | MAL-QRNT, SHRED-ERASE, MEM-SCAN, QRNT-RPR |
| **Investigation** | WEB-SPDR, TAG-GEN, CONF-CAT, BTQ-FPT, PROP-INJ |
| **File explorer** | AUTO-AUD, DRP-ZONE, WAV-CCH |
| **Dashboard layout** | CANVAS-DRG, AXIS-RESIZE, BPRNT-SAVE |

Full UI mapping: `ui/src/lib/specUiCapabilities.ts`

## Tests

```powershell
python -m pytest tests/test_spec_catalog.py tests/test_wave_*.py -q
```

## Demo library

Seed a walkthrough tree without touching your real library:

```powershell
python scripts/seed_demo_library.py
# creates docs/demo/library/ with sample WAV + sidecars
```

## Related docs

- [CHANGELOG — 1.0.2](CHANGELOG.md#web-ui--api-102)
- [Feature guide](FEATURE_GUIDE.md)
- [Configuration](CONFIGURATION.md)
