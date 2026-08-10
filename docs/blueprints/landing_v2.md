# landing_v2 blueprint

Цель `landing_v2` — превратить главный публичный `/` из набора маркетинговых секций в живой командный центр AI-сотрудников. Пользователь должен не просто прочитать promise, а сразу увидеть продуктовую механику: поставить задачу, увидеть агента в работе, понять контроль/безопасность, посчитать экономический эффект и перейти в демо или заявку.

## Позиционирование

Главное сообщение:

> Запустите цифровых сотрудников в своём контуре: агенты, задачи, знания, граф связей, коммуникации и документы в одной платформе.

Почему это сильнее типового SaaS-лендинга:

- Zapier продаёт AI teammates и масштаб интеграций.
- n8n продаёт контроль через видимый workflow/canvas.
- Relevance AI продаёт ROI и операционные метрики агентов.
- Gumloop продаёт workplace agents, security и governance.
- Lindy продаёт личный эффект, social proof и быстрое “time back”.

Наша выигрышная ставка: не “ещё один агент”, а управляемый B2B-контур, где агент действует рядом с AI Studio, Worktracker, Knowledge Base, NetWorkle, Sync и Documents, а бизнес видит работу, стоимость, trace, источники, роли и границы данных.

## Жёсткие frontend-ограничения

Источник канона: `.cursor/rules/frontend.mdc` и проектный `frontend-engineer` skill.

- Главный лендинг мигрируем в marketing Design System, не создаём новую DS.
- Новый код не добавляет `--landing-*`.
- `apps/frontend/ui/styles/landing.css` остаётся deprecated alias layer для legacy.
- Shared visual primitives добавляются в `core/frontend/static/lib/styles/shared/marketing-section.styles.js`.
- Новые semantic tokens добавляются в `core/frontend/static/assets/css/tokens.css`.
- CTA — `<platform-button>`, не локальные `.btn-*`.
- Карточки — `.glass-medium.glass-interactive` или core/shared primitive.
- Public routes остаются dark theme locked и без auth-blocking `/api/auth/me`.
- Global Lara на public routes не показывается; guest demo использует свой `flow-ui-drawer`.
- Все тексты — i18n `landing` ru/en. Без hardcoded пользовательского текста в JS.
- Визуальная динамика обязана уважать `prefers-reduced-motion`.

## Текущий baseline

Существующие сильные части:

- [landing-page.js](../../apps/frontend/ui/pages/landing-page.js) уже собирает публичный `/` из секций.
- [landing-hero.js](../../apps/frontend/ui/components/landing/landing-hero.js) уже содержит public search, режимы quick/deep/research и file attach.
- [landing-home-demo-agents.js](../../apps/frontend/ui/components/landing/landing-home-demo-agents.js) уже показывает guest demo agents через `flow-ui-drawer`.
- [landing-roi-calculator.js](../../apps/frontend/ui/components/landing/landing-roi-calculator.js) уже даёт основу ROI-механики.
- [product-landing-page.js](../../apps/frontend/ui/components/product-landing/product-landing-page.js) уже показывает правильный декларативный подход для `/products/*`.
- [marketing-section.styles.js](../../core/frontend/static/lib/styles/shared/marketing-section.styles.js) уже содержит core marketing layouts.

Текущий долг, который `landing_v2` должен снять:

- Legacy `--landing-*` широко используется в секциях.
- Много локальных `rgba(...)`/hex fallback в компонентных стилях.
- Есть `unsafeHTML` для переносов строк в переводах.
- Часть CTA сделана raw `<button>` или `glass-button`, а не `platform-button`.
- Главный `/` архитектурно отличается от продуктовых посадочных страниц.

## UX-структура

### 1. Hero: `Command Center`

Задача: за 5–10 секунд объяснить продукт и дать попробовать действие.

Содержание:

- Badge: “AI workforce platform”.
- H1: “Цифровые сотрудники для процессов, знаний и коммуникаций”.
- Lede: “AI Studio строит агентов, Worktracker ведёт задачи и очереди, Knowledge Base даёт источники, NetWorkle связывает сущности, Sync и Documents закрывают рабочий контур.”
- Primary CTA: “Попробовать цифрового сотрудника”.
- Secondary CTA: “Собрать сценарий”.
- Inline command input: “Опишите задачу для агента…”.
- Hero visual: живой workbench, где задача проходит стадии:
  1. `Запрос принят`
  2. `Создан WorkItem`
  3. `Агент выбрал tools`
  4. `Нашёл источники`
  5. `Обновил сущности`
  6. `Подготовил результат`

Динамика:

- Лёгкая step animation на CSS variables.
- Активный модуль подсвечивает соответствующий продукт: AI Studio, Worktracker, Knowledge Base, NetWorkle, Sync, Documents.
- При `prefers-reduced-motion: reduce` показывается статичный финальный state.

Технически:

- Новый component: `apps/frontend/ui/components/landing-v2/landing-v2-command-hero.js`.
- Стили общих паттернов: `marketing-command-*` в `marketing-section.styles.js`.
- Reuse текущей search/file attach логики только после выделения в helper/component, чтобы не копировать `landing-hero.js`.

### 2. Live demo: `Try an AI employee`

Задача: пользователь должен почувствовать продукт, а не читать обещания.

Содержание:

- 3–5 карточек цифровых сотрудников из текущего `frontend/landing_agents_load`.
- Карточки не просто “avatar + text”, а “role + trigger + tools + expected result”.
- Primary action: “Запустить демо”.
- Secondary action: “Нанять в свой процесс”.

Динамика:

- При клике открывается существующий guest `flow-ui-drawer`.
- Перед открытием можно показать короткую transition panel: “создаём guest session”.
- После закрытия drawer показываем contextual CTA: “Собрать такого для моей компании”.

Технически:

- Существующий BFF и factories сохраняются:
  - `frontend/landing_agents_load`
  - `frontend/landing_demo_session`
- Новый компонент должен заменить/поглотить `landing-home-demo-agents.js`, но не менять backend contract.
- Нормализация карточек остаётся fail-closed в resource/request или локально через явные проверки без fallback-форм.

### 3. System map: `One perimeter`

Задача: объяснить, почему продукты платформы — не набор ссылок, а единая система выполнения работы.

Содержание:

- Центральный node: “WorkItem / Agent task”.
- Вокруг nodes:
  - AI Studio — логика и orchestration.
  - Worktracker — WorkItem, очереди, HITL, агентные задачи и канбан.
  - Knowledge Base — источники и RAG.
  - NetWorkle — graph/context.
  - Sync — chat/calls/handoff.
  - Documents — files/collaboration.
- Для каждого node: 1-line value + “what happens in the task”.

Динамика:

- Scroll-driven highlight: при входе секции проходит task path по nodes.
- На hover/focus node раскрывает мини-пример.
- Mobile: вертикальный timeline вместо radial map.

Технически:

- Новый shared style group: `marketing-system-map-*`.
- Возможный reusable component: `apps/frontend/ui/components/landing-v2/landing-v2-system-map.js`.
- Никаких canvas/WebGL на MVP. CSS/SVG достаточно.

### 4. Proof strip: `Control, not magic`

Задача: закрыть B2B-возражения: безопасность, стоимость, аудит, модели, on-prem.

Содержание:

- Traceable execution.
- WorkItem lifecycle and queue ownership.
- HITL handoff and operator completion.
- Source-grounded answers.
- Cost per run / budgets.
- Model policy / provider routing.
- Tenant isolation.
- Cloud / hybrid / on-prem.
- 152-ФЗ / РФ hosting / legal entity billing.

Динамика:

- Animated numbers только если есть честные product/platform numbers.
- Если нет backend metrics для public, использовать non-misleading labels: “контроль стоимости”, “trace выполнения”, “изоляция компаний”.

Технически:

- Reuse core UI concepts: `platform-trace-viewer` можно показывать как static miniature/screenshot-like panel, но не дублировать trace viewer logic в landing.
- Если нужен компактный marketing metric primitive — добавить в shared marketing styles или core UI Kit, а не в `apps/frontend`.

### 5. Use-case board: `Pick your workflow`

Задача: дать buyer persona быстрый путь к “это про меня”.

Карточки:

- Support: “ответы по базе + эскалация”.
- Sales/CRM: “лиды, follow-up, graph context”.
- Docs/Ops: “регламенты, договоры, документы”.
- Engineering/Sync: “инциденты, Git context, командные обсуждения”.
- Operators/HITL: “очереди, ручное решение исключений, возврат ответа агенту”.
- Back office: “повторяющиеся процессы, WorkItem-доски и отчёты”.

Каждая карточка:

- Trigger.
- Agent action.
- Systems touched.
- Outcome metric.
- CTA: “Показать сценарий”.

Динамика:

- Click переключает правую visual panel с task timeline.
- Mobile: accordion/details.

### 6. ROI calculator v2

Задача: превратить интерес в заявку.

Поля:

- Сценарий: support / sales / docs / engineering / operators-HITL / back office.
- Численность.
- Количество обращений/задач в месяц.
- Средняя стоимость ручной обработки.
- Доля автоматизации.
- Ориентировочная стоимость внедрения.

Результат:

- Экономия в месяц/год.
- Окупаемость.
- Какие продукты платформы нужны.
- CTA: “Получить аудит процессов”.

Технически:

- Можно эволюционно расширить [landing-roi-calculator.js](../../apps/frontend/ui/components/landing/landing-roi-calculator.js).
- Новые поля лучше делать через `<platform-field>` если это form-like UI; `input type="range"` допустим как whitelisted raw input, но стили — через shared tokens.
- Формат чисел — через `formatPlatformNumber` / `formatPlatformCurrencyRub` с локалью из `state.i18n.locale`.

### 7. Product deep links

Задача: не терять тех, кто уже понял конкретный продукт.

Содержание:

- AI Studio.
- Worktracker.
- Knowledge Base.
- NetWorkle.
- Sync.
- Documents.
- Agent desktop.

Для каждого:

- One-liner.
- Screenshot/visual.
- CTA на `/products/*`, `/worktracker` или `/agent`.

Технически:

- Reuse декларативные product configs и `land-product-images.js`.
- Worktracker уже есть в platform service catalog как `id: 'worktracker'`; MVP может вести в `/worktracker`, а отдельную `/products/worktracker` стоит добавлять только если нужен public product deep dive.
- Не дублировать product page copy в main landing; main landing только маршрутизирует интерес.

### 8. Trust, cases, FAQ, final CTA

Задача: закрыть procurement и финальную конверсию.

Trust:

- Deployment options.
- Data isolation.
- Billing/legal docs.
- Support/onboarding.

Cases:

- Должны быть конкретнее текущих общих формулировок.
- До появления реальных case studies не писать неподтверждённые claims.

FAQ:

- “Можно ли on-prem?”
- “Где хранятся данные?”
- “Можно ли использовать свои модели?”
- “Как считается стоимость?”
- “Чем отличается от Zapier/n8n/Lindy?”
- “Можно ли попробовать без регистрации?”

Final CTA:

- Primary: “Запустить демо”.
- Secondary: “Запросить аудит”.

## Рекомендуемая component architecture

Новая структура:

```text
apps/frontend/ui/
  pages/
    landing-v2-page.js
  components/
    landing-v2/
      landing-v2-command-hero.js
      landing-v2-demo-agents.js
      landing-v2-system-map.js
      landing-v2-proof-strip.js
      landing-v2-use-case-board.js
      landing-v2-roi-calculator.js
      landing-v2-product-deep-links.js
      landing-v2-faq.js
      landing-v2-final-cta.js
```

Первый implementation flag:

- Вариант A: заменить route `landing` сразу после готовности.
- Вариант B: временно добавить internal route `landing-v2` без public navigation, затем переключить `landing`.

Предпочтение: вариант B для быстрой визуальной итерации и screenshot sanity без риска для текущего `/`.

## Shared/core work

Добавить/расширить в [marketing-section.styles.js](../../core/frontend/static/lib/styles/shared/marketing-section.styles.js):

- `marketingCommandHeroStyles`
- `marketingAgentWorkbenchStyles`
- `marketingSystemMapStyles`
- `marketingProofStripStyles`
- `marketingUseCaseBoardStyles`
- `marketingRoiStyles`

Добавить semantic tokens в `tokens.css`, если их нет:

- `--marketing-orbit-line`
- `--marketing-orbit-node-bg`
- `--marketing-orbit-node-border`
- `--marketing-workbench-bg`
- `--marketing-workbench-border`
- `--marketing-proof-positive`
- `--marketing-proof-warning`
- `--marketing-motion-distance-sm`
- `--marketing-motion-distance-md`

Не добавлять:

- `--landing-v2-*`
- локальные brand hex
- локальные `box-shadow`/`backdrop-filter`, если это повторяемый primitive

## Copy skeleton

H1:

```text
Цифровые сотрудники для процессов, знаний и коммуникаций
```

Lede:

```text
Собирайте AI-агентов в AI Studio, ведите задачи и HITL в Worktracker, подключайте знания, граф связей, чат, звонки и документы — в облаке, гибриде или своём контуре.
```

Hero command placeholder:

```text
Например: обработай заявку клиента, найди контекст и подготовь ответ
```

Proof headline:

```text
Не магия. Управляемое выполнение.
```

System map headline:

```text
Один агент. Вся работа в одном контуре.
```

ROI headline:

```text
Посчитайте эффект до внедрения
```

Final CTA headline:

```text
Запустите первого цифрового сотрудника на реальном процессе
```

## Responsive rules

Desktop `1440x1024`:

- Hero занимает первый viewport, но не блокирует scroll.
- Workbench справа или по центру, CTA и command input видны без scroll.
- System map может быть radial/graph.

Tablet:

- Hero в 1 column + workbench below.
- Product/system nodes — 2-column grid.

Mobile `390x844` / `430x932`:

- No horizontal scroll.
- Header remains current landing header.
- Hero H1 не должен вытеснять command input ниже первого экрана полностью.
- System map превращается в timeline.
- Floating CTA не перекрывает drawer, keyboard и form controls.
- Demo cards — single column.

## Motion rules

Допустимые motion:

- opacity/transform only.
- CSS transitions from shared tokens.
- section-enter highlight through `IntersectionObserver`.
- no long-running animation on large images except subtle glow/orbit.

Запрещённые motion для MVP:

- WebGL/canvas hero.
- Heavy scroll-jacking.
- Autoplay video as first content.
- Blocking animation before content visibility.

Reduced motion:

```css
@media (prefers-reduced-motion: reduce) {
    animation: none;
    transition-duration: 0.01ms;
}
```

## Data and events

Use existing:

- `frontend/landing_agents_load`
- `frontend/landing_demo_session`
- `frontend/public_search_*`
- `frontend/lead_submit`

Worktracker-specific:

- Public landing не читает приватные WorkItem пользователя.
- Worktracker в hero/system map показывается как product/workflow visual или через demo data.
- Authenticated deep link ведёт в `/worktracker`.
- Если позже понадобится real task preview для authenticated users, использовать только platform WorkItem factories/components (`platform/work_item_*`, `<platform-work-item-*>`), без локальных task cards.

Potential new frontend-only slice:

- `frontend/landing_v2_demo_state` only if multiple sections need shared selected use-case / selected demo.
- Prefer local component state for MVP.

No new backend required for phase 1.

Backend optional for phase 2:

- Public anonymized landing metrics endpoint if we want real animated proof numbers.
- Lead enrichment fields: selected use-case, ROI inputs, clicked demo card.

## SEO/meta

Keep existing public meta flow in `FrontendApp._syncPublicHtmlMeta`.

Update `landing.meta.home_title` and `landing.meta.home_description` only after copy finalization.

Recommended description direction:

```text
{platformName} — платформа цифровых сотрудников: AI Studio, Worktracker, Knowledge Base, NetWorkle, Sync и Документы в одном B2B-контуре. AI-агенты, WorkItem, HITL, RAG, граф связей, коммуникации, документы, контроль стоимости и on-premise.
```

Structured data can remain `WebSite` + `Organization` + `SoftwareApplication` for MVP.

## Implementation phases

### Phase 0 — foundation

- Add `docs/blueprints/landing_v2.md`.
- Decide route strategy: hidden `landing-v2` vs direct replacement.
- Add missing marketing shared style groups.
- Add missing marketing tokens.
- No visual behavior changes on `/`.

### Phase 1 — parallel landing v2 page

- Create `landing-v2-page.js`.
- Create command hero, system map, proof strip, final CTA.
- Reuse current `landing-header`/`landing-footer`.
- Add ru/en i18n keys.
- Add hidden route if approved.
- Run static canon checks.

### Phase 2 — live demo and ROI

- Port demo agents to `landing-v2-demo-agents`.
- Extend ROI calculator v2.
- Add use-case board.
- Keep existing BFF contracts.
- Add event-safe CTA flows.

### Phase 3 — replace `/`

- Switch `landing` route render to `<landing-v2-page>`.
- Keep old components for one release only if rollback is needed.
- Remove old sections after validation.
- Shrink deprecated `landing.css` usage.

### Phase 4 — proof and polish

- Add real public proof metrics if backend supports it.
- Add Playwright screenshots for desktop/mobile.
- Add docs scenario after implementation screenshots exist.
- Tune performance and LCP.

## Acceptance criteria

UX:

- User sees primary value and CTA in first viewport.
- User can run a demo agent without registration.
- User can understand product architecture without reading long text.
- User can estimate ROI.
- User can route to product pages or lead form.

Engineering:

- No new `--landing-*`.
- No local brand hex/rgba in new landing v2 components.
- No `unsafeHTML`.
- CTA buttons use `<platform-button>`.
- No direct `fetch`/`httpRequest` in pages/components.
- No direct resource imports in pages/components.
- All user text in ru/en `landing.json`.
- `make check-ui-canon` passes.
- `make check-ui-factories` passes.
- `make check-i18n` and `make check-i18n-keys` pass.
- Desktop sanity at `1440x1024`.
- Mobile sanity at `390x844` or `430x932`.
- No horizontal scroll.
- `prefers-reduced-motion` respected.

Performance:

- Hero content visible before non-critical images load.
- Main hero image has explicit dimensions if used.
- Demo agent cards lazy-load images.
- No layout shift from floating CTA/header.
- No blocking analytics before first render.

## Open decisions

1. Brand tone: more enterprise/control or more bold “digital employees”?
2. Should `/` lead with demo agents or command hero?
3. Do we add hidden `/landing-v2` route first?
4. Which product gets primary CTA for authenticated users: AI Studio or digital workers catalog?
5. Do we want competitor comparison on page, or keep it implicit in FAQ?
6. Do we have real public metrics, or keep proof qualitative until backend metrics are available?

Recommended defaults:

- Tone: enterprise/control with dynamic product feel.
- First screen: command hero.
- Route: hidden `landing-v2` first.
- Authenticated primary CTA: AI Studio.
- Anonymous primary CTA: demo digital workers.
- Competitor comparison: FAQ only.
- Metrics: qualitative in MVP, real metrics later.
