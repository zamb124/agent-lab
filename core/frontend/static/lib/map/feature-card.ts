/**
 * Карточка фичи карты — аналог балуна Яндекс.Карт для <platform-map>.
 *
 * Рендер — чистая функция в HTML-строку (MapLibre Popup принимает строку).
 * Для каждого канонического слоя — типизированная карточка по whitelist-
 * свойствам `apps/geo/layers.py`; неизвестный слой — таблица свойств.
 * Hover-хинт — `featureHintText`: короткий заголовок без разметки.
 */

export interface FeatureCardInput {
    layer: string;
    properties: Record<string, unknown>;
}

type Translate = (key: string) => string;

const _ESC_RE = /[&<>"]/g;
const _ESC_MAP: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
};

export function escHtml(v: unknown): string {
    return String(v ?? '').replace(_ESC_RE, (c) => _ESC_MAP[c]!);
}

/** Короткий заголовок фичи для hover-хинта и шапки карточки. */
export function featureTitle({ layer, properties }: FeatureCardInput): string {
    const display = properties['display_name'] ?? properties['name'];
    if (typeof display === 'string' && display !== '') return display;
    if (layer === 'addresses') {
        const street = String(properties['street'] ?? '');
        const house = String(properties['housenumber'] ?? '');
        const joined = `${street} ${house}`.trim();
        if (joined !== '') return joined;
    }
    if (layer === 'roads' && typeof properties['highway'] === 'string') {
        return properties['highway'];
    }
    if (layer === 'barriers' && typeof properties['barrier'] === 'string') {
        return properties['barrier'];
    }
    return layer;
}

function _row(key: string, value: unknown): string {
    return `<div class="pm-card-row"><span>${escHtml(key)}</span><b>${escHtml(value)}</b></div>`;
}

function _rows(props: Record<string, unknown>, keys: readonly string[]): string {
    return keys
        .filter((k) => props[k] !== undefined && props[k] !== null && props[k] !== '')
        .map((k) => _row(k, props[k]))
        .join('');
}

/** Карточка слоя: заголовок + значимые поля + таблица остальных whitelist-полей. */
export function renderFeatureCard(
    input: FeatureCardInput,
    t: Translate,
    layerColor: string | null,
): string {
    const { layer, properties } = input;
    const title = featureTitle(input);
    const layerLabel = layer !== '' ? t(`layers.${layer}`) : '';
    const chip = layerLabel !== '' && layerLabel !== `layers.${layer}`
        ? `<span class="pm-card-chip"${layerColor ? ` style="--chip:${escHtml(layerColor)}"` : ''}>${escHtml(layerLabel)}</span>`
        : '';
    let body: string;
    switch (layer) {
        case 'addresses': {
            const city = String(properties['city'] ?? '');
            body =
                (city !== '' ? `<div class="pm-card-sub">${escHtml(city)}</div>` : '') +
                _rows(properties, ['street', 'housenumber']);
            break;
        }
        case 'roads': {
            body = _rows(properties, ['highway', 'oneway', 'length_m', 'osm_way_id']);
            break;
        }
        case 'barriers': {
            const blocks = ['block_car', 'block_foot', 'block_bike', 'block_scooter']
                .filter((k) => properties[k] === true)
                .map((k) => `<span class="pm-card-tag">${escHtml(k.replace('block_', ''))}</span>`)
                .join('');
            body =
                (properties['barrier'] ? _row('barrier', properties['barrier']) : '') +
                (blocks !== '' ? `<div class="pm-card-tags">${blocks}</div>` : '');
            break;
        }
        case 'restrictions': {
            body = _rows(properties, ['restriction', 'from_way', 'to_way', 'via_node']);
            break;
        }
        case 'regions': {
            body = _rows(properties, ['kind', 'enabled', 'title']);
            break;
        }
        case 'signals': {
            body = _rows(properties, ['osm_node_id']);
            break;
        }
        default: {
            body = Object.entries(properties)
                .filter(([k]) => k !== 'layer' && !k.startsWith('__'))
                .slice(0, 10)
                .map(([k, v]) => _row(k, v))
                .join('');
        }
    }
    const coords = properties['__coords'] as string | undefined;
    const footer =
        coords !== undefined
            ? `<div class="pm-card-footer"><span class="pm-card-coords">${escHtml(coords)}</span></div>`
            : '';
    return `<div class="pm-card"><div class="pm-card-head"><div class="pm-card-title">${escHtml(title)}</div>${chip}</div>${body}${footer}</div>`;
}
