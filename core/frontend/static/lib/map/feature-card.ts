/**
 * Карточка фичи карты — аналог балуна Яндекс.Карт для <platform-map>.
 *
 * Рендер — чистая функция в HTML-строку (MapLibre Popup принимает строку).
 * Для каждого канонического слоя — типизированная карточка по whitelist-
 * свойствам `apps/geo/layers.py`; неизвестный слой — читаемая таблица полей.
 * Hover-хинт — `featureTitle`: короткий заголовок без разметки.
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
        const joined = `${String(properties['street'] ?? '')} ${String(properties['housenumber'] ?? '')}`.trim();
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

const _NONEMPTY = (v: unknown): v is string => typeof v === 'string' && v !== '';

/** Локализованное значение: булевы/числовые/строковые — безопасный вывод. */
function _val(v: unknown): string {
    if (v === true) return 'yes';
    if (v === false) return 'no';
    return String(v ?? '');
}

function _row(label: string, value: string): string {
    return `<div class="pm-card-row"><span class="pm-card-row-k">${escHtml(label)}</span><span class="pm-card-row-v">${escHtml(value)}</span></div>`;
}

function _fmtLen(m: unknown): string {
    const n = Number(m);
    if (!Number.isFinite(n) || n <= 0) return '';
    return n >= 1000 ? `${(n / 1000).toFixed(n >= 10_000 ? 0 : 1)} km` : `${Math.round(n)} m`;
}

function _osm(kind: string, id: unknown): string {
    const v = String(id ?? '');
    return v === '' ? '' : `OSM ${kind} #${v}`;
}

/** Типизированная карточка слоя: заголовок + значимая meta-строка. */
export function renderFeatureCard(
    input: FeatureCardInput,
    t: Translate,
    layerColor: string | null,
): string {
    const { layer, properties } = input;
    const layerLabel = layer !== '' ? t(`layers.${layer}`) : '';
    const chip =
        layerLabel !== '' && layerLabel !== `layers.${layer}`
            ? `<div class="pm-card-kind"><span class="pm-card-dot"${layerColor ? ` style="--chip:${escHtml(layerColor)}"` : ''}></span>${escHtml(layerLabel)}</div>`
            : '';

    let title = featureTitle(input);
    let sub = '';
    let meta = '';
    let tags = '';
    const rows: string[] = [];

    switch (layer) {
        case 'addresses': {
            const street = String(properties['street'] ?? '');
            const house = String(properties['housenumber'] ?? '');
            const joined = `${street} ${house}`.trim();
            if (joined !== '') title = joined;
            sub = String(properties['city'] ?? '');
            break;
        }
        case 'roads': {
            const name = String(properties['name'] ?? '');
            if (name !== '') title = name;
            const parts: string[] = [];
            const len = _fmtLen(properties['length_m']);
            if (len !== '') parts.push(len);
            if (properties['oneway'] === true || properties['oneway'] === 'yes') parts.push(t('map.card_one_way'));
            if (parts.length > 0) sub = parts.join(' · ');
            const osm = _osm('way', properties['osm_way_id']);
            if (osm !== '') meta = osm;
            break;
        }
        case 'barriers': {
            const kind = String(properties['barrier'] ?? '');
            const kindLabel = kind !== '' ? t(`map.card_barrier_${kind}`) : '';
            if (kindLabel !== '' && kindLabel !== `map.card_barrier_${kind}`) title = kindLabel;
            else if (kind !== '') title = kind;
            const blocked = (['car', 'foot', 'bike', 'scooter'] as const).filter(
                (mode) => properties[`block_${mode}`] === true,
            );
            const icons: Record<string, string> = { car: '🚗', foot: '🚶', bike: '🚲', scooter: '🛴' };
            if (blocked.length > 0) {
                tags = `<div class="pm-card-tags" title="${escHtml(t('map.card_blocks'))}">${blocked
                    .map((mode) => `<span class="pm-card-tag">${icons[mode]}</span>`)
                    .join('')}</div>`;
            }
            const osm = _osm('node', properties['osm_node_id']);
            if (osm !== '') meta = osm;
            break;
        }
        case 'restrictions': {
            const kind = String(properties['restriction'] ?? '');
            const kindLabel = kind !== '' ? t(`map.card_restriction_${kind}`) : '';
            if (kindLabel !== '' && kindLabel !== `map.card_restriction_${kind}`) title = kindLabel;
            else if (kind !== '') title = kind;
            const parts = [_osm('relation', properties['osm_relation_id'])];
            const fromTo = [properties['from_way'], properties['to_way']]
                .map((v) => String(v ?? ''))
                .filter((v) => v !== '')
                .join(' → ');
            if (fromTo !== '') parts.push(fromTo);
            meta = parts.filter((v) => v !== '').join(' · ');
            break;
        }
        case 'regions': {
            const regTitle = String(properties['title'] ?? '');
            if (regTitle !== '') title = regTitle;
            const parts = [String(properties['kind'] ?? ''), String(properties['name'] ?? '')].filter((v) => v !== '');
            if (parts.length > 0) sub = parts.join(' · ');
            if (properties['enabled'] === true) meta = t('map.card_enabled');
            else if (properties['enabled'] === false) meta = t('map.card_disabled');
            break;
        }
        case 'signals': {
            title = t('map.card_signal');
            const osm = _osm('node', properties['osm_node_id']);
            if (osm !== '') meta = osm;
            break;
        }
        default: {
            // Неизвестный слой — читаемая таблица первых полей.
            for (const [k, v] of Object.entries(properties)) {
                if (k === 'layer' || k.startsWith('__') || v === '' || v === null || v === undefined) continue;
                if (rows.length >= 6) break;
                rows.push(_row(k.replace(/_/g, ' '), _val(v)));
            }
        }
    }

    const coords = properties['__coords'] as string | undefined;
    const footer =
        coords !== undefined
            ? `<div class="pm-card-footer"><span class="pm-card-coords">${escHtml(coords)}</span></div>`
            : meta !== ''
              ? `<div class="pm-card-footer"><span class="pm-card-meta">${escHtml(meta)}</span></div>`
              : '';
    const metaRow = coords !== undefined && meta !== '' ? `<div class="pm-card-meta">${escHtml(meta)}</div>` : '';

    if (title === '' && sub === '' && rows.length === 0 && meta === '') return '';
    return (
        `<div class="pm-card">${chip}` +
        `<div class="pm-card-title">${escHtml(title)}</div>` +
        (sub !== '' ? `<div class="pm-card-sub">${escHtml(sub)}</div>` : '') +
        (rows.length > 0 ? `<div class="pm-card-rows">${rows.join('')}</div>` : '') +
        tags +
        metaRow +
        footer +
        `</div>`
    );
}
