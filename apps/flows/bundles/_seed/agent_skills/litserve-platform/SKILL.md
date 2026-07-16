---
name: litserve-platform
description: LitServe provider UI guidance for local AI model status, capabilities, compatibility, GPU deployment, and troubleshooting. Load from the LitServe SPA or for local model questions.
---

# LitServe provider

## Goal

Explain local AI provider state and guide safe UI operations without bypassing the platform AI layer.

## Procedure

1. Use `provider`, `model`, `capability`, route and compact UI context as the current selection.
2. Distinguish model availability from capability compatibility: embeddings, rerank, STT, TTS and VAD are separate capabilities.
3. Explain status, configuration and troubleshooting in terms shown by the LitServe UI.
4. Load root `docs-knowledge` for platform instructions and `platform-workspace` → `web-research` for public model documentation.
5. For application code, require model resolution and execution through `core.ai`; do not propose provider-specific clients.

## Capability boundary

This skill unlocks no operational tools. Starting, stopping, installing, deleting or reconfiguring LitServe models has no Lara tool contract. Guide the user in the UI and never claim the provider changed state.

## Security

Do not request API keys, infrastructure credentials or secret configuration values.
