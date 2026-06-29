---
title: "Документация Humanitec"
description: "Современная документация Humanitec: быстрый старт, API, руководства и автособранные инструкции интерфейса."
---

<div class="docs-home">
  <p class="docs-page-kicker">Документация Humanitec</p>
  <p class="docs-lead">Документация для платформы ИИ-агентов, Flows, Sync, NetWorkle и RAG. Здесь есть быстрый старт, публичные API и автособранные E2E-инструкции с реальными скриншотами интерфейса.</p>
  <div class="docs-hero-actions">
    <a class="docs-button docs-button-primary" href="quickstart/">Начать интеграцию</a>
    <a class="docs-button" href="api/">Открыть API</a>
  </div>
  <div class="docs-home-visual">
    <div class="docs-product-shot">
      <img src="scenarios/flows/screenshots/001.png" alt="Интерфейс Flows в Humanitec">
    </div>
    <div class="docs-endpoint-panel">
      <span class="docs-method">POST</span>
      <code>/flows/api/v1/{flow_id}</code>
      <p>JSON-RPC вызовы для отправки сообщений агенту, streaming-ответов и управления задачами.</p>
    </div>
  </div>
</div>

## Разделы

<div class="docs-card-grid">
  <a class="docs-card docs-card-primary" href="quickstart/">
    <span class="docs-card-kicker">Старт</span>
    <h2>Быстрый старт</h2>
    <p>Минимальный путь до первого запроса к агенту через A2A JSON-RPC.</p>
  </a>
  <a class="docs-card" href="scenarios/platform/">
    <span class="docs-card-kicker">Основы</span>
    <h2>Основные инструкции</h2>
    <p>Вход на сайт, Dashboard, список сервисов и меню пользователя простым языком.</p>
  </a>
  <a class="docs-card" href="api/">
    <span class="docs-card-kicker">API</span>
    <h2>API</h2>
    <p>Автогенерация из OpenAPI: Flows, Frontend и другие публичные сервисы.</p>
  </a>
  <a class="docs-card" href="scenarios/">
    <span class="docs-card-kicker">E2E</span>
    <h2>Инструкции</h2>
    <p>UI-проверки, шаги и скриншоты, которые попадают в документацию из тестов.</p>
  </a>
  <a class="docs-card" href="start-here/">
    <span class="docs-card-kicker">Старт</span>
    <h2>Начни отсюда</h2>
    <p>Готовые маршруты для нового пользователя, разработчика и команды в Sync.</p>
  </a>
</div>

## Как устроена сборка

<div class="docs-path-grid">
  <div>
    <strong>1. OpenAPI</strong>
    <p>Схемы из <code>docs/openapi</code> превращаются в Markdown-страницы API.</p>
  </div>
  <div>
    <strong>2. Инструкции</strong>
    <p><code>README.md</code> и скриншоты из <code>docs/scenarios</code> собираются в разделы продукта.</p>
  </div>
  <div>
    <strong>3. Production</strong>
    <p>Zensical собирает статический портал в <code>documentation-dist</code>, который попадает в full Docker image.</p>
  </div>
</div>
