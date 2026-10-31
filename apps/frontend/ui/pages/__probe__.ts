import type { ControllerFor } from '@platform/lib/base/use-resource.js';
declare const c: ControllerFor<'frontend/lead_requests'>;
const rawItems = c.items;
const list = Array.isArray(rawItems) ? rawItems : [];
const l = list[0];
const d = l.created_at;
const bad: typeof d = 123;
export { bad };
