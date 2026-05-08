/**
 * Sync-обёртки над core hash-string utils.
 *
 * Канон: hueFromString / initialsFromName живут в
 * `@platform/lib/utils/hash-string.js`. Здесь — только sync-специфика
 * (CSS-переменная `--sync-avatar-h`).
 */

import { hueFromString, initialsFromName } from '@platform/lib/utils/hash-string.js';

export { hueFromString, initialsFromName };

/** CSS custom property для пастельного аватара (читает токены с :root). */
export function syncAvatarHueVar(seed) {
    return `--sync-avatar-h: ${hueFromString(typeof seed === 'string' ? seed : '')}`;
}
