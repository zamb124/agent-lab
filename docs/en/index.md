---
title: "Humanitec Documentation"
description: "Modern Humanitec documentation hub: quickstart, API reference, guides, and generated UI instructions."
---

<div class="docs-home">
  <p class="docs-page-kicker">Humanitec Docs</p>
  <p class="docs-lead">Documentation for the AI agent, Flows, Sync, NetWorkle, and RAG platform. Start with a working A2A request, browse generated API reference, or inspect UI instructions with real screenshots.</p>
  <div class="docs-hero-actions">
    <a class="docs-button docs-button-primary" href="quickstart/">Start building</a>
    <a class="docs-button" href="api/">Open API</a>
  </div>
  <div class="docs-home-visual">
    <div class="docs-product-shot">
      <img src="scenarios/sync/spaces/create-space/screenshots/001.png" alt="Humanitec Sync interface">
    </div>
    <div class="docs-endpoint-panel">
      <span class="docs-method">POST</span>
      <code>/flows/api/v1/{flow_id}</code>
      <p>JSON-RPC calls for agent messages, streaming responses, and task control.</p>
    </div>
  </div>
</div>

## Sections

<div class="docs-card-grid">
  <a class="docs-card docs-card-primary" href="quickstart/">
    <span class="docs-card-kicker">Start</span>
    <h2>Quickstart</h2>
    <p>The shortest path to the first A2A JSON-RPC request.</p>
  </a>
  <a class="docs-card" href="scenarios/platform/">
    <span class="docs-card-kicker">Basics</span>
    <h2>Platform Basics</h2>
    <p>Site entry, Dashboard, service list, and user menu for new users.</p>
  </a>
  <a class="docs-card" href="api/">
    <span class="docs-card-kicker">Reference</span>
    <h2>API Reference</h2>
    <p>Generated from OpenAPI for Flows, Frontend, and public services.</p>
  </a>
  <a class="docs-card" href="scenarios/">
    <span class="docs-card-kicker">E2E</span>
    <h2>Instructions</h2>
    <p>UI checks, steps, and screenshots generated from instruction README files.</p>
  </a>
  <a class="docs-card" href="guides/">
    <span class="docs-card-kicker">Guides</span>
    <h2>Guides</h2>
    <p>Overview pages and entry points for product teams.</p>
  </a>
</div>

## Build Pipeline

<div class="docs-path-grid">
  <div>
    <strong>1. OpenAPI</strong>
    <p>Schemas in <code>docs/openapi</code> are converted into API Markdown pages.</p>
  </div>
  <div>
    <strong>2. Instructions</strong>
    <p><code>README.md</code>, <code>README.en.md</code>, and screenshots are assembled into product instruction sections.</p>
  </div>
  <div>
    <strong>3. Production</strong>
    <p>Zensical builds the static portal into <code>documentation-dist</code>, then the full Docker image ships it.</p>
  </div>
</div>
