/**
 * Типы api_keys — view-модели UI без служебных wire-полей.
 * Type-only leaf: resources и pages/modals импортируют отсюда,
 * чтобы pages/modals не зависели от `events/resources/*` напрямую.
 */

import type { ResourceItem } from '@platform/lib/events/factories/resource-collection.js';

/**
 * View-форма ключа для UI: wire `ApiKeyRecord` несёт служебные поля
 * (company_id, key_hash, created_by) — на клиент уходит только безопасная часть.
 */
export interface ApiKeyListItem extends ResourceItem {
    key_id: string;
    name: string;
    scopes: string[];
    key_prefix: string;
    created_at: string;
    last_used: string | null;
}
