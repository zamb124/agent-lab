/**
 * Shared surface builders for Flow UI page starters.
 */
import { flowUIComponent as component } from '../component-factory.js';
import { assignExplicitGridRows } from '../../layout/grid-normalize.js';

/** Template copy is document content the flow owner edits later, so it is
 *  materialized once in the editor locale instead of staying a localized map. */
export function copy(locale, ru, en) {
    return locale === 'ru' ? ru : en;
}

/**
 * Templates declare spans (and columns for a two-up row); rows left on `auto` are
 * resolved here by the same normalize the editor uses, so a starter page opens
 * with real cells instead of CSS auto-placement.
 */
export function surface(surfaceId, components, dataModel) {
    const placed = structuredClone(components);
    assignExplicitGridRows({ components: placed });
    return Object.freeze({
        surface_id: surfaceId,
        root_component_id: 'root',
        components: Object.freeze(placed),
        data_model: Object.freeze({
            content: Object.freeze(dataModel.content || {}),
            values: Object.freeze(dataModel.values || {}),
            system: Object.freeze(dataModel.system || {}),
        }),
        owner: 'platform',
        send_data_model: true,
    });
}

export function requiredCheck(message) {
    return Object.freeze({ function: 'required', message: message || '', pattern: null, value: null });
}

export { component };
