# secops-theme 1.0.0 → 1.0.1: contrast fixes to upstream

Local copy: `clients/web/static/vendor/secops-theme/tokens.css` (patched in place, Version 1.0.1).
Audit: `.venv/bin/python .impeccable/audit/vendor_tokens_audit.py [path/to/tokens.css]` — 1.0.0 has 12 failures, 1.0.1 has 0.

Criteria: each text/status token must reach 4.5:1 (WCAG AA) against every surface token, and each status
token also on its own `-bg` tint layered over the resting surfaces (canvas, low, container, high, modal, table rows).
Hue is kept; only lightness changes (smallest change that passes). Severity steps stay visually distinct (ΔE ≥ 24).

## Dark (`:root, [data-theme="dark"]`)
| Token | 1.0.0 | 1.0.1 | Worst contrast before → after |
|---|---|---|---|
| `--secops-text-secondary` | `#9aa0a6` | `#aaafb4` | 3.84 → 4.59 (surface-active) |
| `--secops-status-critical` | `#ff5a50` | `#ff8e87` | 3.30 → 4.57 |
| `--secops-status-high` | `#fa7b17` | `#fb9544` | 3.82 → 4.58 |
| `--secops-status-low` | `#24c1e0` | `#2fc4e2` | 4.40 → 4.56 (own tint on surface-high) |
| `--secops-status-success` | `#54ab98` | `#78bdae` | 3.61 → 4.57 (own tint on surface-high) |
| `--secops-chip-event` | `#d272ff` | `#db90ff` | 3.66 → 4.56 |

The dark `-bg` / `-border` rgba tints can stay as they are (they still derive from the 1.0.0 hues, which is fine).

## Light (`[data-theme="light"]`)
| Token | 1.0.0 | 1.0.1 | Worst contrast before → after |
|---|---|---|---|
| `--secops-text-accent` | `#1a73e8` | `#0b57d0` | 3.74 → 5.30 (same value as `--secops-text-code`) |
| `--secops-status-critical` | `#d93025` | `#c5221f` | 3.96 → 4.81 |
| `--secops-status-high` | `#e37400` | `#a35400` | 2.58 → 4.55 |
| `--secops-status-medium` | `#b06000` | `#7a5c00` | 3.86 → 5.19 |
| `--secops-status-low` | `#007b83` | `#00747c` | 4.19 → 4.60 |

`--secops-status-medium` moves toward olive-amber so it stays distinguishable from the darker `status-high`.
The old medium, `#b06000`, was only 19 ΔE from the old high.

## Unchanged, noted for upstream
- `--secops-cta-primary` `#1a73e8` with white text is 4.51:1, which only just passes. Keep it as a fill; don't use it as a text colour.
- The light `--secops-border-focus` `#1a73e8` is 3.74:1, which meets the 3:1 minimum for non-text elements.
- `--secops-font-size-xs: 10px` is below the 11px minimum we use.
