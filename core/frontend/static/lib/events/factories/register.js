/**
 * resources(...factories) и effects(...factories) — helpers для PlatformApp.
 *
 * Идея: вместо ручной сборки `getServiceSlices` / `getServiceEffects` с
 * перечислением каждого слайса и эффекта, сервис передаёт массив фабрик
 * (любая из createAsyncOp / createResourceCollection / createCursorList /
 * createFacets / createForm / createSlice), а helper извлекает из них
 * slices и effect-функции.
 *
 *   import { acceptInviteOp } from '.../accept-invite.js';
 *   import { apiKeysResource } from '.../api-keys.js';
 *
 *   const { slices, effects } = collectFactories([acceptInviteOp, apiKeysResource]);
 *
 * `collectFactories` детерминированно возвращает:
 *   - slices: { [sliceKey]: { reducer, initial } } — для всех 6 видов фабрик.
 *   - effects: Array<(event, ctx) => void> — фабрики с полем `effect`
 *     регистрируют ровно один effect; `createSlice` без `effect` и в
 *     массив effects не попадает (только slice/reducer).
 *
 * При коллизии sliceKey — Error: фабрики одного сервиса должны иметь
 * уникальные name (контролируется через _internal registry, но дополнительно
 * проверяется здесь на уровне финальной сборки).
 */

const KNOWN_KINDS = new Set(['async-op', 'resource-collection', 'cursor-list', 'facets', 'form', 'slice']);

export function collectFactories(factories) {
    if (!Array.isArray(factories)) {
        throw new Error('collectFactories: factories array required');
    }
    const slices = {};
    const effects = [];
    for (const factory of factories) {
        if (!factory || typeof factory !== 'object' || !KNOWN_KINDS.has(factory.kind)) {
            throw new Error(`collectFactories: unknown factory kind "${factory && factory.kind}"`);
        }
        if (slices[factory.sliceKey]) {
            throw new Error(`collectFactories: duplicate sliceKey "${factory.sliceKey}" (factory: ${factory.name})`);
        }
        slices[factory.sliceKey] = factory.slice;
        if (typeof factory.effect === 'function') {
            const fn = factory.effect.bind(factory);
            fn.__factoryName = factory.name;
            effects.push(fn);
        }
    }
    return { slices, effects };
}

/**
 * resources(...factories) — sugar для тех, кто предпочитает spread-форму:
 *   const { slices, effects } = resources(acceptInvite, apiKeys, embed);
 */
export function resources(...factories) {
    return collectFactories(factories);
}
