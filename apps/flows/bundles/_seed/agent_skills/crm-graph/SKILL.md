---
name: crm-graph
description: CRM relationship graph — list/delete relationships, relationship types, related neighborhood, shortest path.
allowed-tools: crm_list_relationships crm_delete_relationship crm_list_relationship_types crm_entity_related crm_shortest_path
---

# CRM graph

## Goal

Navigate and maintain NetWorkle relationship edges (not the 3d/mindmap UI chrome).

## Procedure

1. Types catalog — `crm_list_relationship_types` when choosing `relationship_type`.
2. Edges for an entity — `crm_list_relationships(entity_id=…)`.
3. Remove a wrong edge — `crm_delete_relationship(relationship_id)` after confirmation.
4. One-hop neighborhood — `crm_entity_related(entity_id, direction=both|incoming|outgoing)`.
5. Path between two nodes — `crm_shortest_path(from_entity_id, to_entity_id)`.
6. Creating a new edge — load `crm-entities` → `crm_create_relationship`.

## Rules

- Never invent `relationship_id` / `entity_id`.
- Graph 3d / mindmap visualization is UI-only — do not claim to open canvas tools.
