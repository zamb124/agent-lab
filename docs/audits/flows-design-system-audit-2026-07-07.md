# Flows Design System Audit

**Дата:** 2026-07-07  
**Scope:** `apps/flows/ui/**` (pages, modals, components) vs core UI Kit, `flows.mdc`, CI gates #17–#29  
**Figma reference:** [Networkle / Макеты / node 30:556](https://www.figma.com/design/6d1JW3Ohwzos6PLyfgPAQS/Networkle?node-id=30-556)  
**Режим:** read-only аудит, без правок UI

---

## 1. Executive Summary

| Область | Статус |
|---------|--------|
| CI `check-ui-canon` (#23–#29) | **PASS** |
| CI `check-field-canon` | **PASS** |
| `make ui` (Vitest 881 + WTR 444) | **PASS** |
| `make check-i18n-keys` (flows path) | **PASS** (no-op target) |
| Glass triplet budget (#28) | **12/12 — budget exhausted (P0)** |
| Raw `<button>` allowlist (#24) | **6 files (P3 debt)** |
| Figma flows-specific frames | **Отсутствуют** на canvas «Макеты» |

**Top 5 gaps (по impact):**

1. **P0 — CI glass triplet at limit:** любой новый inline glass panel в flows блокирует PR до миграции одного из 12 allowlisted файлов.
2. **P1 — `flows-mcp-servers-modal.js`:** legacy `.mcp-presets` chip row вместо `<platform-picker-card>`; inconsistent с library-picker / flow-create.
3. **P1 — `color: white` hardcode** в `flows-flow-create-modal.js` (вне CI #23).
4. **P1 — Local `.form-field` / `.form-error` CSS** в 4 modals (field canon drift).
5. **P2 — Raw checkbox/radio `<input>`** в 3 файлах вместо `platform-field` boolean/radio.

**Figma scope note:** canvas «Макеты» (30:556) содержит только CRM workspace («Работа с заметками», «Управление сущностями»). Сравнение flows ведётся по **общему Networkle workspace rhythm** (1440×1024, sidebar, header, search, pagination), не по pixel-match flows-экранов.

---

## 2. CI Baseline (Phase 0)

Запуск: 2026-07-07.

| Команда | Exit | Результат |
|---------|------|-----------|
| `make check-ui-canon` | 0 | `check_ui_canon: OK` |
| `make check-field-canon` | 0 | `check_field_canon: OK` |
| `make ui` | 0 | Vitest **881 passed**; WTR **444 passed**; `ui: OK` |
| `make check-i18n-keys apps/flows/ui` | 0 | Makefile no-op (`Nothing to be done`) — глобальный gate в `make ui` уже прогнан |

### Gates #23–#29 (flows-specific)

| Gate | Rule | Status | Count / notes |
|------|------|--------|---------------|
| #23 | hex/rgba outside canvas | PASS | 0 hits |
| #24 | raw `<button>` | PASS | 0 outside allowlist; **6 allowlisted** |
| #25 | legacy button CSS | PASS | 0 hits |
| #26 | `<glass-button>` | PASS | 0 hits |
| #27 | literal `--platform-button-icon-size: Npx` | PASS | 0 hits |
| #28 | inline glass triplet | PASS (at limit) | **12/12 files** |
| #29 | duplicate `action_cancel` i18n | PASS | only `flows.common` |

### Appendix: Gate #28 file list (glass triplet)

Файл считается triplet, если содержит и `glass-solid-subtle`, и `glass-border-subtle`:

1. `apps/flows/ui/components/editors/flows-code-editor.js`
2. `apps/flows/ui/modals/flows-code-docs-modal.js`
3. `apps/flows/ui/components/nodes/flows-llm-node-editor.js`
4. `apps/flows/ui/components/editors/flows-code-workbench.js`
5. `apps/flows/ui/components/nodes/flows-external-api-editor.js`
6. `apps/flows/ui/components/nodes/flows-channel-node-editor.js`
7. `apps/flows/ui/components/nodes/flows-mcp-node-editor.js`
8. `apps/flows/ui/modals/flows-mcp-servers-modal.js`
9. `apps/flows/ui/components/nodes/flows-resource-node-editor.js`
10. `apps/flows/ui/components/nodes/flows-base-node-editor.js`
11. `apps/flows/ui/components/nodes/flows-reflection-node-editor.js`
12. `apps/flows/ui/modals/flows-library-picker-modal.js`

### Appendix: Gate #24 allowlist (raw `<button>`)

| File | Reason (from `check_ui_canon.sh`) |
|------|-----------------------------------|
| `components/flow-canvas/flows-flow-canvas.js` | Canvas chrome |
| `components/evaluation/flows-evaluation-results-matrix.js` | run-head, cell-button |
| `components/evaluation/flows-evaluation-compare-panel.js` | run-chip |
| `modals/flows-durable-history-modal.js` | branch-chip, event-row |
| `components/editor/flows-execution-panel.js` | resize-handle |
| `components/nodes/flows-base-node-editor.js` | dataflow-chip, file-ref |

---

## 3. Surface Inventory (Phase 1)

**Denominator:** 81 UI surface files = 4 pages + 28 modals + 49 components.

### 3.1 Pages (4)

| File | Breadcrumbs | Chrome / notes |
|------|-------------|----------------|
| `pages/flows-home-page.js` | No (home) | Marketing + catalog; glass surfaces inline |
| `pages/flow-editor-page.js` | Yes | Canvas host, floating panel, execution panel |
| `pages/chat-page.js` | Yes | `<platform-chat>` |
| `pages/flows-evaluation-page.js` | Yes | 3-column eval layout |

### 3.2 Modals (28)

All 28 extend `PlatformModal` / `PlatformFormModal`.

| Modal | Picker-card | Modal-search | Glass triplet | Notes |
|-------|-------------|--------------|---------------|-------|
| `flows-api-console-modal.js` | — | — | partial (panelShell) | Large `--modal-width: 1360px` |
| `flows-branch-create-modal.js` | — | — | — | Local `.form-error` |
| `flows-browser-preview-modal.js` | — | — | — | |
| `flows-canvas-help-modal.js` | — | — | — | |
| `flows-code-docs-modal.js` | — | Yes | **triplet** | |
| `flows-code-modal.js` | — | — | — | |
| `flows-code-node-drop-modal.js` | Yes | — | — | Migrated |
| `flows-durable-history-modal.js` | — | — | solid-only | Raw button allowlist |
| `flows-edge-condition-modal.js` | — | — | — | glassStyles; local `.form-field` |
| `flows-embedded-tool-config-modal.js` | — | — | — | |
| `flows-flow-create-modal.js` | Yes | Yes | — | glassStyles; **`color: white`** |
| `flows-flow-edit-modal.js` | — | — | — | |
| `flows-incoming-policy-modal.js` | Yes | — | — | Migrated |
| `flows-integrations-modal.js` | — | — | — | |
| `flows-library-picker-modal.js` | Yes | Yes | **triplet** | |
| `flows-logs-modal.js` | — | — | — | |
| `flows-mcp-servers-modal.js` | **No** | Yes | **triplet** | `.mcp-presets` legacy |
| `flows-preview-share-modal.js` | — | — | — | |
| `flows-raw-json-modal.js` | — | — | — | |
| `flows-sessions-modal.js` | — | — | solid-only | |
| `flows-span-details-modal.js` | — | — | — | |
| `flows-state-modal.js` | — | — | — | |
| `flows-tool-create-modal.js` | — | — | — | glassStyles |
| `flows-tracing-modal.js` | — | — | — | |
| `flows-trigger-editor-modal.js` | — | — | — | Local `.form-error`; raw checkbox |
| `flows-triggers-modal.js` | — | — | — | |
| `flows-variable-editor-modal.js` | — | — | — | |
| `flows-variables-modal.js` | — | — | — | |

### 3.3 Components by group (49)

| Group | Count | Key files |
|-------|-------|-----------|
| **Editor chrome** | 11 | `flows-editor-header`, `flows-execution-panel`, `flows-floating-panel`, `flows-node-types-sidebar`, `flows-bottom-toolbar`, property panels |
| **Canvas** | 5 | `flows-flow-canvas`, sticky-note, context-menu, edge-label |
| **Node editors** | 12 | `flows-base-node-editor`, `flows-llm-node-editor`, `flows-code-node-editor`, … |
| **Editors / workbench** | 5 | `flows-code-editor`, `flows-code-workbench`, `flows-llm-config-editor`, `flows-state-mapping-editor`, `flows-parameters-schema-form` |
| **Evaluation** | 7 | case-editor, run-toolbar, suite-sidebar, results-matrix, compare-panel, transcript, trace-panel |
| **Resources** | 5 | base/files/code/llm/llm-context resource editors |
| **Catalog / chrome** | 4 | `flows-catalog-list`, `flow-card`, `flows-sidebar`, `branch-item` |
| **Other** | 2 | `flows-node-run-control`, `flows-code-language-icon` |

### 3.4 Out of scope (not in 81)

- `apps/flows/ui/events/**` — factories/resources (canon via `check_ui_factories`)
- `apps/flows/ui/_helpers/**` — utilities (1 i18n gap file)
- `apps/flows/ui/app/flows-app.js` — app shell

---

## 4. Violation Matrix (Phase 2)

### 4.1 CI-enforced (all PASS)

No active violations. Debt = allowlists at capacity.

### 4.2 Tech debt outside CI

| File | Violation | Severity | Gate ref | Remediation |
|------|-----------|----------|----------|-------------|
| *(12 files)* | Inline glass triplet | **P0** | #28 at limit | Import `glassStyles` / `panelShellStyles` |
| `modals/flows-mcp-servers-modal.js` | `.mcp-presets` chips, not picker-card | **P1** | flows.mdc picker canon | Migrate presets to `<platform-picker-card>` |
| `modals/flows-flow-create-modal.js` | `color: white` L194 | **P1** | #23 gap | `var(--text-inverse)` or token |
| `modals/flows-edge-condition-modal.js` | `.form-field`, `.form-error` | **P1** | field canon | Remove after platform-field layout |
| `modals/flows-branch-create-modal.js` | `.form-error` | **P1** | field canon | Use platform-field error slot |
| `modals/flows-flow-create-modal.js` | `.form-error` | **P1** | field canon | Same |
| `modals/flows-trigger-editor-modal.js` | `.form-error` | **P1** | field canon | Same |
| `modals/flows-trigger-editor-modal.js` | raw `type="checkbox"` | **P2** | field canon | `platform-field type="boolean"` |
| `components/editors/flows-parameters-schema-form.js` | raw checkbox + CSS | **P2** | field canon | platform-field boolean |
| `components/nodes/flows-llm-node-editor.js` | raw radio/checkbox | **P2** | field canon | platform-field / segmented-control |
| `_helpers/flows-python-completion-catalog.js` | local `escapeHtmlForCompletion` | **P2** | utility canon | `@platform/lib/utils/escapeHtml` |
| `modals/flows-api-console-modal.js` | `.mode-tabs` local CSS | **P2** | flows.mdc | Already has segmented-control elsewhere; unify tabs |
| `components/editor/flows-execution-panel.js` | `.tab-toolbar`, `.tab-panel` | **P2** | flows.mdc | Consider segmented-control for panel tabs |
| *(12 solid-only files)* | `glass-solid-subtle` without triplet | **P3** | style consolidation | Prefer shared styles when touching file |
| *(6 allowlist files)* | raw `<button>` | **P3** | #24 | platform-button or `article role="button"` |
| *(8 files, 27 lines)* | Cyrillic in comments/strings | **P3** | i18n gaps script | Comments OK per rules; review user-visible strings |

### 4.3 Zero violations confirmed

| Pattern | Result |
|---------|--------|
| `dispatch(CoreEvents` in pages/modals/components | **0 hits** |
| `<glass-button>` | **0 hits** |
| Legacy `.action-btn` / `.icon-btn` / … | **0 hits** |
| Literal `--platform-button-icon-size: Npx` | **0 hits** |
| Raw `<select>` / `<textarea>` in flows UI components | **0 hits** (field-canon PASS) |

---

## 5. Component Adoption (Phase 3)

Denominator: **81** surface files (pages + modals + components).

| Primitive | Files using | Adoption | Target surfaces | Gap |
|-----------|-------------|----------|-----------------|-----|
| `platform-button` | 51 | **63%** | All action chrome | 6 allowlisted raw buttons; canvas sticky-note |
| `platform-field` | 31 | **38%** | All typed inputs | checkbox/radio in 3 files; some modals without fields |
| `platform-segmented-control` | 19 | **23%** | Mode/tabs toggles | api-console `.mode-tabs`; execution-panel tab CSS |
| `platform-picker-card` | 4 | **5%** (of all) | Card selection modals | **mcp-servers** not migrated |
| `platform-modal-search-field` | 7 | **9%** | Searchable lists | triggers-modal, sessions-modal, integrations-modal lack it |
| `platform-json-editor` | 10 | **12%** | JSON config surfaces | raw-json-modal uses CM directly (acceptable for debug) |
| `glassStyles` / `panelShellStyles` | 11 | **14%** | Glass panels | 12 triplet + 12 solid-only still inline |
| `platform-breadcrumbs` | 3 | **75%** of subpages | editor, chat, eval | home excluded by design |
| `platform-chat` | 4 | N/A | chat surfaces | Correct on chat-page + execution drawer |

### Shared styles adoption detail

**Files importing `glassStyles` or `panelShellStyles` (11):**

- `flow-card.js`, `flows-node-types-sidebar.js`
- Modals: `flow-create`, `edge-condition`, `tool-create`, `api-console`
- Evaluation: `case-editor`, `compare-panel`, `results-matrix`, `trace-panel`, `transcript`

**24 files** use `glass-solid-subtle`; **12** are triplet (CI budget), **12** solid-only (not counted by #28).

---

## 6. Figma vs Tokens vs Tests (Phase 4)

### 6.1 Figma «Макеты» structure

| Section | Node | Content |
|---------|------|---------|
| Макеты | 30:556 | Root canvas |
| Работа с заметками | 322:5450 | CRM notes workspace |
| Управление сущностями | 551:4804 | CRM entity table |

**No Flows/Agent frames** found by text/metadata search under 30:556.

### 6.2 Figma variables (section 322:5450 sample)

| Figma token | Value |
|-------------|-------|
| Light/font | `#222222` |
| Light/background | `#FFFFFF` |
| Light/violet | `#99A6F9` |
| H1 | Onest Bold 36/44 |
| body | Onest Regular 16 |
| caption | Onest Regular 12 |

Runtime mapping: platform `tokens.css` uses semantic `--text-primary`, `--accent`, `--glass-*` — not 1:1 hex from Figma file (by design: Figma = reference).

### 6.3 Rhythm comparison

| Dimension | Networkle / Design Standard | Flows runtime | Match |
|-----------|----------------------------|---------------|-------|
| Viewport | 1440×1024 | WTR uses fixture viewport; editor full-bleed | Partial — no global 1440 visual baseline test |
| Sidebar | 100px | `platform-sidebar` in `flows-app` (core) | **Yes** (core) |
| Header row | ~60px total feel | `--flows-editor-chrome-row-min-height: 40px` × 2 rows + padding | **Close** — 2-row header ~80–88px |
| Chrome buttons | 44px round (marketing) / 32px chrome | WTR: icon-only **27–33px** (compact/dense) | **Yes** — chrome tier, not primary 44px |
| Toolbar shell | 48px | `--flows-toolbar-shell-min-height: 48px` | **Yes** — tested in `flows-chrome-height.spec.js` |
| Side panel | 324px / 400px | Eval sidebar **260px**; execution panel **min(460px)**; floating panel **94vw** | **Intentional divergence** — flows editor ≠ CRM list |
| Search field | 440×44 | `platform-modal-search-field` in 7 surfaces | Partial — not all searchable modals |
| Modal width | ~640 content | Variable: 640–1360px by modal | **By design** — api-console wide |

### 6.4 Key `--flows-*` tokens (`tokens.css`)

```text
--flows-micro-control-size: 28px
--flows-chrome-control-size: 32px
--flows-chrome-row-min-height: 40px
--flows-toolbar-shell-min-height: 48px
--flows-sidebar-row-min-height: 42px
--flows-editor-chrome-gap: var(--space-2)
```

### 6.5 Test coverage map

| Area | Spec file | What it guards |
|------|-----------|----------------|
| Chrome density | `tests/frontend_core/browser/flows/flows-chrome-height.spec.js` | Header icon buttons 27–33px; toolbar min-height 48px |
| Field height | `tests/frontend_core/browser/flows/field-height-canon.spec.js` | platform-field density |
| Editor header | `tests/frontend_core/browser/flows/editor-header-flow-settings.spec.js` | Header actions / settings |
| Catalog | `tests/frontend_core/browser/flows/flows-catalog-list-toolbar.spec.js` | List toolbar |
| Chat | `tests/frontend_core/browser/flows/chat-page-toolbar.spec.js`, `flows-chat-input.spec.js`, `platform-chat-theme.spec.js` | Chat chrome |
| Node editors | `tests/frontend_core/browser/flows/node-editors.spec.js`, `llm-config-editor.spec.js` | Editor forms |
| DS consumer L3 | `tests/ui/design-system/flows/library-picker-cards.spec.js` | picker-card contract |
| DS consumer L3 | `tests/ui/design-system/flows/flow-create-presets.spec.js` | flow-create presets |
| DS consumer L3 | `tests/ui/design-system/flows/incoming-policy-picker.spec.js` | incoming policy cards |

**Total flows WTR specs:** 23 under `tests/frontend_core/browser/flows/` + 3 design-system consumer specs.

**Gaps (manual / future visual baselines):**

- No 1440×1024 screenshot regression per page (home, editor, eval, chat)
- No visual test for `flows-mcp-servers-modal` picker migration
- No mobile shell test for flows-specific routes (relies on core bottom-nav)
- Figma pixel parity not automated (and not expected without flows frames)

---

## 7. Prioritized Backlog (Phase 5)

### P0 — CI regression risk

| ID | Item | Wave |
|----|------|------|
| P0-1 | Glass triplet 12/12 — zero headroom for new panels | **Wave A** |
| P0-2 | Document triplet file list in PR checklist for flows UI | Process |

### P1 — User-visible canon drift

| ID | Item | Wave |
|----|------|------|
| P1-1 | `flows-mcp-servers-modal` → `platform-picker-card` | **Wave D** |
| P1-2 | Remove `color: white` in flow-create modal | **Wave D** |
| P1-3 | Remove local `.form-field` / `.form-error` (4 modals) | **Wave C** |
| P1-4 | Add `platform-modal-search-field` to searchable modals without it | **Wave D** |

### P2 — Maintainability

| ID | Item | Wave |
|----|------|------|
| P2-1 | Migrate 12 glass triplet files to shared styles | **Wave A** |
| P2-2 | platform-field for checkbox/radio (3 files) | **Wave C** |
| P2-3 | Replace `escapeHtmlForCompletion` duplicate | **Wave D** |
| P2-4 | Unify api-console / execution-panel tabs with segmented-control | **Wave B/C** |
| P2-5 | Migrate 12 solid-only glass files when touched | **Wave A** |

### P3 — Allowlisted exceptions

| ID | Item | Wave |
|----|------|------|
| P3-1 | Eliminate #24 allowlist (6 files) | **Wave B** |
| P3-2 | Cyrillic comment cleanup (non-user-facing, low priority) | Optional |

### Recommended remediation waves (future cycle)

| Wave | Scope | CI impact |
|------|-------|-----------|
| **A** | 12 glass triplet → `glassStyles`/`panelShellStyles`; lower #28 max | Frees budget |
| **B** | 6 raw-button allowlist → platform-button / semantic article | Shrink #24 |
| **C** | platform-field boolean/radio; remove `.form-*` CSS | Extend field-canon |
| **D** | mcp-servers picker-card; white color; utility dedup; search fields | Visual consistency |
| **E** | New CI: `.form-field`, `color: white`, `.mcp-presets` | Prevent regression |
| **F** | Playwright visual baselines (1440 + mobile) per major surface | Figma rhythm guard |

---

## 8. Appendix

### A. Raw CI output (summary)

```text
check_ui_canon: OK
check_field_canon: OK
make ui: Vitest 881 passed; WTR 444 passed; ui: OK
```

### B. i18n gaps (`report_ui_i18n_gaps.py --app flows`)

8 files, 27 lines — predominantly **code comments** in canvas, node editors, helpers. User-visible string in `flows-external-api-defaults.js` (tool descriptions) — review for i18n if exposed in UI.

### C. Inventory totals

| Category | Count |
|----------|-------|
| Pages | 4 |
| Modals | 28 |
| Components | 49 |
| **UI surfaces total** | **81** |
| Full `apps/flows/ui/**/*.js` | 130 |

---

*Audit performed read-only. No production code changed.*

### D. Post Wave F migration (2026-07-07)

- `#24` allowlist: **0** raw `<button>` in `apps/flows/ui`
- Evaluation sidebar/matrix: `--flows-side-panel-width` **324px** (CRM parity)
- Editor header: single-row desktop chrome ~**60px**
- `make ui`: WTR + Vitest green after Wave F
