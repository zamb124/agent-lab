# Design Standard — Figma → tokens.css

Норма — `.cursor/rules/frontend.mdc` § Дизайн: в компонентах только токены `tokens.css` и core-компоненты, локальные hex/rgba запрещены. Этот файл — как переводить макет в код.

Обратное направление — `tokens.css` → Figma Variables: `uv run python -m scripts.tools.figma_tokens sync` (норма `figma.mdc` § Канон 7–9, процедура — SKILL.md § Figma-синк). Меняя токены, прогоняем синк и коммитим `scripts/tools/figma_tokens.snapshot.json`.

## Источники

- Ритм и семантика — базовые макеты Figma `Networkle / Макеты / node 30:556`.
- CSS-слепок макета — [`apps/crm/design/design.css`](apps/crm/design/design.css): только справка, в компонент не копируется.
- Runtime — [`core/frontend/static/assets/css/tokens.css`](core/frontend/static/assets/css/tokens.css), shared styles [`core/frontend/static/lib/styles/shared/`](core/frontend/static/lib/styles/shared/), core-компоненты [`core/frontend/static/lib/components/`](core/frontend/static/lib/components/) и их UIKDS-доки `docs/scenarios/platform/ui-kit/<tag>/`.
- Figma задаёт ритм, код — только токены и core-компоненты. Повторяемый цвет, размер или поведение из макета, которого нет в runtime, — сначала семантический токен или core-компонент, потом использование.

## Продуктовый тон

- Платформа — рабочий SaaS: первый экран страницы — workspace (списки, карточки, редактор, фильтры, таблицы, панель действий). Hero, декоративные блоки, маркетинговые карточные секции и пустые «объясняющие» экраны вместо workflow не делаем.
- Публичный маркетинг (`/`, `/products/*`) — та же DS: `tokens.css` (`--marketing-*`, `--glass-*`, `--text-*`, `--space-*`), `core/frontend/static/lib/styles/shared/marketing-section.styles.ts`, `<platform-button variant="primary">` (текст — `--platform-btn-primary-text`), карточки `.glass-medium.glass-interactive`, страницы продуктов — `ProductLandingPage` + декларативный config в `apps/frontend/ui/pages/products/`. Параллельный `--landing-*` и локальные brand hex не создаются; пробел в визуале маркетинга — токен или shared style в `core/frontend/`.

## Ритм макета

- Desktop — `1440x1024`, вертикальный scroll, плотная сетка; gap и padding `8/12/16/20/24/32` → `--space-*`, литерал px — только разовое geometry-ограничение.
- Рабочие панели content + side panel: в Figma `324/400/461/508px`, gap `24px`, padding `20/24/32px` → `grid-template-columns: minmax(0, 1fr) minmax(320px, 400px)` (или `minmax(360px, 508px)`) и responsive collapse, без absolute-position.
- Контролы (button, input, dropdown, date) — `44px`; строки списков и sidebar — `60px`; icon buttons — `28/32/36/44px` → `--button-height`, `--input-height`, density-атрибуты `<platform-button>` (`--platform-button-icon-size` задаёт компонент), `--field-pill-*`.
- Радиусы: card, note, summary — `--radius-lg` (16px); компактные поверхности — `--radius-md` (12px); кнопки — `--btn-radius` (22px); field pill — `--field-pill-radius` (18px); модалка и bottom sheet — `--radius-2xl`/`--radius-3xl`.
- Mobile — один столбец, sticky chrome через `<platform-top-bar>`, `<platform-bottom-nav>`, `<platform-bottom-sheet>` и safe-area токены `--platform-safe-*`; desktop grid с горизонтальным скроллом на мобиле не оставляем.

## Token mapping

| Figma | Runtime |
|---|---|
| `Light/background #FFFFFF` | light — `--bg-surface`, `--bg-elevated`; dark — `--glass-solid-*` |
| `Light/font #222222` | `--text-primary` |
| muted `rgba(34,34,34,0.3)` | `--text-tertiary` |
| secondary text | `--text-secondary` |
| акценты violet `#99A6F9`, yellow `#FAD17A`, orange `#FF885C`, cyan `#8CE6FD`, rose `#FFAAAB` | `--accent`, `--accent-secondary`, `--accent-gradient`, `--crm-accent-*`, `--crm-summary-*`, `--crm-note-*`, `--crm-note-related-*` |
| success / warning / error / info | `--success`, `--warning`, `--error`, `--info` и их `*-bg`/`*-border` |

Новый смысл — токен `--<svc>-<domain>-<role>` в `tokens.css` (пример существующих: `--crm-summary-*`, `--work-item-state-*`).

## Component mapping

| Figma / задача | Runtime |
|---|---|
| Button, round button | `<platform-button>` (`variant`: `primary`, `accent`, `secondary`, `danger`, `ghost`; `icon-only`, `density`) или классы `buttonStyles`; самописный pill не делаем |
| Text input, dropdown, date input | `<platform-field>` + `fieldPillStyles`; дата — `platform-field type="date"` → `ui_fields.mdc` |
| Modal | `PlatformModal` / `PlatformFormModal` + `<platform-modal-stack>`; размер — `size` и `--modal-width` |
| Note, Daily summary, task list, повторяемая карточка | `glass-card`, `platform-island` или компонент сервиса на semantic tokens; для CRM — сначала `--crm-summary-*`, `--crm-note-*` |
| Sidebar, navigation, header, breadcrumbs | `<platform-service-sidebar>`, `<platform-sidebar-nav-tree>`, `<platform-top-bar>`, `<page-header>`, `<platform-breadcrumbs>` |
| Tags, entity chips, user | `tag-input`, chip на `--crm-note-related-*`, `<platform-user-chip>` для пользователя |

## CSS discipline

- `static styles` в `apps/<svc>/ui/**` описывает только layout текущего компонента и composition. Общие button, input, modal, card, list, chip — в `core/frontend/static/lib/**` или `tokens.css`.
- Не пишем локальные hex/rgb/rgba для brand, accent, surface, text; локальные `box-shadow`, `backdrop-filter`, `border-radius` shared-примитивов; копию классов из `apps/crm/design/design.css`.
- Примитив повторился второй раз в сервисе — semantic token или компонент сервиса; нужен в двух сервисах — core UI Kit.
- Shadow reset `PlatformElement` (`core/frontend/static/lib/platform-element/styles.ts`): `:host { font-family: var(--font-sans) }`, `:host button { font: inherit }`, `:host input, textarea, select { font: inherit; color: inherit }`. `color: inherit` на `:host button` не ставим: специфичность `(0,1,1)` перебивает `.btn-primary`/`.cta-btn`, и в light theme CTA получает тёмный `--text-primary`. Локальный размер `input` пишем как `:host input.<class>`, иначе `font: inherit` съедает кегль.
- Текст на solid primary/accent — `--platform-btn-primary-text`, `--platform-btn-accent-text`, `--text-on-accent`; `--text-inverse` — контраст к фону поверхности, не on-accent.
- Display-типографика — `--text-display-*`, `--tracking-tight`, `--font-semibold`, не отдельная font-family. Смена шрифта — manifest `core/frontend/static/assets/fonts/platform-typography.json` + woff2 в `core/frontend/static/assets/fonts/<family>/` + `@font-face` в `platform-fonts.css` (проверяет `scripts/gates/frontend/platform_typography.py`).

## Responsive sanity

1. Перед закрытием визуальной задачи — desktop `1440x1024`.
2. Затронут shell, страница или модалка — ещё mobile `390x844` или `430x932`.
3. Проверяем: нет overlap, горизонтального скролла, обрезанного текста; ритм и плотность совпадают с Figma.
4. Скриншоты — через браузер (`make app`, URL сервиса) или Playwright сценарий UIKDS (`make ui-doc`).
