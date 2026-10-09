/**
 * Team Search — typeahead подсказок users по имени/email внутри платформы.
 *
 * Бэкенд: GET /crm/api/team/search?q=...&limit=...  → ListResponse[UserSearchResult]
 *   item: { user_id, name, email?, avatar_url? }
 *
 * Используется share-modal для выбора получателя гранта.
 */

import { createFacets } from '@platform/lib/events/index.js';

export const teamSearchFacets = createFacets({
    name: 'crm/team_search',
    baseUrl: '/crm/api/team',
    facets: { users: 'search' },
    debounceMs: 250,
    minQueryLength: 2,
    pageSize: 20,
});
