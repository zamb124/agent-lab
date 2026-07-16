---
name: console-platform
description: Platform Console service guidance for profile, companies, team, integrations, API keys, secrets, billing, and AI settings. Load from the Console entry or for account administration questions.
---

# Platform Console

## Goal

Guide authenticated users through the Platform Console without inventing administrative capabilities.

## Procedure

1. Use `route_key`, `screen`, `company_id` and the compact UI context to identify the current console area.
2. Explain the shortest UI path for profile, company membership, team, integrations, API keys, secrets, tariff, billing, observability, notifications, brand or AI settings.
3. Treat displayed identifiers and statuses as facts; do not infer hidden configuration.
4. Never request full secret, token or API-key values. Explain where the user can rotate or replace them.
5. If the task requires product documentation, load root `docs-knowledge`; if it becomes service work, load that service root from the Tier-1 index.

## Capability boundary

This skill intentionally unlocks no operational tools. Console mutations have no Lara tool contract. Give UI instructions and never claim that an account, key, integration, tariff or setting was changed.
