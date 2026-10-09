/**
 * CRM domain push event-type constants (slash-канон).
 *
 * Pages/modals импортируют отсюда; литералы `'crm/…/…'` вне
 * `events/resources` / `events/types` запрещены CI
 * (`scripts/check_platform_events_canon.py`).
 */

export const CRM_NOTE_UPDATED = 'crm/note/updated';
export const CRM_TASK_UPDATED = 'crm/task/updated';
export const CRM_DAILY_SUMMARY_UPDATED = 'crm/daily_summary/updated';
export const CRM_PERIOD_SUMMARY_UPDATED = 'crm/period_summary/updated';
export const CRM_SUGGEST_UPDATED = 'crm/suggest/updated';
