import type { OpControllerOf } from '@platform/lib/base/use-resource.js';
import type { PlatformFactoryRegistry } from '@platform/lib/events/factory-registry.js';
declare const c: OpControllerOf<PlatformFactoryRegistry['wiki/page_save']>;
const p = c.run({ wiki_page_id: 'x' });
type R = Awaited<typeof p>;
const bad: R = 'not-a-page';
export { bad };
