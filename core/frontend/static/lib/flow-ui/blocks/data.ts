/** Данные: data_table, chart (SVG без библиотек), json_view, file_card, file_list. */

import { isPlainRecord } from '../../events/payload.js';
import { html, nothing } from '../../lit-shim.js';
import { formatFileSize } from '../../utils/format-file-size.js';
import { blockText as text, valueAtPath } from '../runtime/templating.js';
import { flowUIGlyph } from '../utils/glyph.js';
import { openFlowUISessionFile } from '../utils/open-session-file.js';
import { flowUIText } from '../utils/text.js';
import type { FlowUiBlockRenderer, FlowUiRecord, FlowUiRenderContext } from '../runtime/flow-ui-store.js';

const PALETTE = ['#6ea8fe', '#3ecf8e', '#f6c343', '#ff718d', '#b197fc', '#4dd4ac', '#ffa94d', '#74c0fc'];

function columnSpec(raw: unknown): { key: string; label: unknown } {
    if (!isPlainRecord(raw)) throw new Error('flow-ui: data_table column must be an object');
    const key = raw.key;
    if (typeof key !== 'string' || key.length === 0) {
        throw new Error('flow-ui: data_table column.key must be a non-empty string');
    }
    return { key, label: raw.label };
}

function declaredColumns(raw: unknown): { key: string; label: unknown }[] | null {
    if (raw === undefined || raw === null) return null;
    if (!Array.isArray(raw)) throw new Error('flow-ui: data_table columns must be a list');
    const columns: { key: string; label: unknown }[] = [];
    for (const column of raw) columns.push(columnSpec(column));
    return columns;
}

function inferredColumns(rows: unknown[]): { key: string; label: string }[] {
    const first = rows[0];
    if (first === undefined) return [];
    if (!isPlainRecord(first)) throw new Error('flow-ui: data_table row must be an object');
    return Object.keys(first).map((key) => ({ key, label: key }));
}

function rowActionOf(value: unknown): FlowUiRecord | null {
    if (value === null || value === undefined) return null;
    if (!isPlainRecord(value)) throw new Error('flow-ui: data_table row_action must be an object');
    return value;
}

function actionPayload(payload: unknown, row: unknown): Record<string, unknown> {
    const base: Record<string, unknown> = {};
    if (payload !== undefined && payload !== null) {
        if (!isPlainRecord(payload)) throw new Error('flow-ui: data_table row_action.payload must be an object');
        for (const [key, value] of Object.entries(payload)) base[key] = value;
    }
    base.row = row;
    return base;
}

function cellValue(row: unknown, key: string): unknown {
    if (!isPlainRecord(row)) throw new Error('flow-ui: data_table row must be an object');
    return row[key];
}

function fileRecord(file: unknown): FlowUiRecord {
    if (!isPlainRecord(file)) throw new Error('flow-ui: file_card expects FileRef with original_name');
    return file;
}

function cellText(value: unknown): string {
    if (value === null || value === undefined) return '';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
}

function shown(value: string | null): string {
    return value === null ? '' : value;
}

function fileById(ctx: FlowUiRenderContext, fileId: unknown): FlowUiRecord | null {
    const files: unknown[] = Array.isArray(ctx.state.files) ? ctx.state.files : [];
    for (const file of files) {
        if (isPlainRecord(file) && file.file_id === fileId) return file;
    }
    return null;
}

export function fileCard(ctx: FlowUiRenderContext, file: FlowUiRecord | null | undefined) {
    if (!file || typeof file !== 'object' || typeof file.original_name !== 'string') {
        throw new Error('flow-ui: file_card expects FileRef with original_name');
    }
    const openable = typeof file.file_id === 'string' && file.file_id !== '';
    return html`<a class="fu-file" href=${typeof file.url === 'string' ? file.url : '#'} data-file-id=${typeof file.file_id === 'string' ? file.file_id : nothing}
        @click=${(event: Event) => { if (!openable) return; event.preventDefault(); openFlowUISessionFile(file); }}>
        ${flowUIGlyph('file-text', 18, ctx.platformUiOrigin)}
        <span class="name">${file.original_name}</span>
        <span class="meta">${typeof file.file_size === 'number' ? formatFileSize(file.file_size) : ''}</span>
    </a>`;
}

function numeric(row: FlowUiRecord, key: string): number {
    const value = Number(row[key]);
    return Number.isFinite(value) ? value : 0;
}

function pieChart(points: FlowUiRecord[], x: string, y: string) {
    const total = points.reduce((sum: number, point) => sum + Math.max(numeric(point, y), 0), 0) || 1;
    let angle = -Math.PI / 2;
    const slices = points.map((point, index) => {
        const share = Math.max(numeric(point, y), 0) / total;
        const start = angle;
        angle += share * Math.PI * 2;
        const large = share > 0.5 ? 1 : 0;
        const [sx, sy] = [50 + 40 * Math.cos(start), 50 + 40 * Math.sin(start)];
        const [ex, ey] = [50 + 40 * Math.cos(angle), 50 + 40 * Math.sin(angle)];
        return html`<path d=${`M50 50 L${sx} ${sy} A40 40 0 ${large} 1 ${ex} ${ey} Z`} fill=${PALETTE[index % PALETTE.length]}>
            <title>${cellText(point[x])}: ${cellText(point[y])}</title></path>`;
    });
    return { svg: html`<svg viewBox="0 0 100 100" role="img">${slices}</svg>`, legend: points.map((point, index) => ({ label: cellText(point[x]), color: PALETTE[index % PALETTE.length] })) };
}

function xyChart(kind: string, points: FlowUiRecord[], x: string, ys: string[]) {
    const width = 320; const height = 160; const pad = 8;
    const max = Math.max(1, ...points.flatMap((point) => ys.map((key) => numeric(point, key))));
    const scaleY = (value: number) => height - pad - (Math.max(value, 0) / max) * (height - pad * 2);
    const step = (width - pad * 2) / Math.max(points.length, 1);
    const series = ys.map((key, seriesIndex) => {
        const color = PALETTE[seriesIndex % PALETTE.length];
        if (kind === 'bar') {
            const barWidth = Math.max(2, (step - 4) / ys.length);
            return points.map((point, index) => html`<rect x=${pad + index * step + 2 + seriesIndex * barWidth}
                y=${scaleY(numeric(point, key))} width=${barWidth} height=${height - pad - scaleY(numeric(point, key))} fill=${color} rx="1.5">
                <title>${cellText(point[x])} · ${key}: ${cellText(point[key])}</title></rect>`);
        }
        const coords = points.map((point, index) => `${pad + index * step + step / 2},${scaleY(numeric(point, key))}`);
        const line = html`<polyline points=${coords.join(' ')} fill="none" stroke=${color} stroke-width="2" stroke-linejoin="round"></polyline>`;
        if (kind === 'line') return line;
        const first = `${pad + step / 2},${height - pad}`;
        const last = `${pad + (points.length - 1) * step + step / 2},${height - pad}`;
        return html`<polygon points=${`${first} ${coords.join(' ')} ${last}`} fill=${color} opacity="0.22"></polygon>${line}`;
    });
    const labels = points.map((point, index) => html`<text x=${pad + index * step + step / 2} y=${height + 12} font-size="9" text-anchor="middle" fill="currentColor" opacity="0.7">${cellText(point[x])}</text>`);
    return {
        svg: html`<svg viewBox=${`0 0 ${width} ${height + 18}`} role="img"><line x1=${pad} y1=${height - pad} x2=${width - pad} y2=${height - pad} stroke="currentColor" opacity="0.25"></line>${series}${labels}</svg>`,
        legend: ys.map((key, index) => ({ label: key, color: PALETTE[index % PALETTE.length] })),
    };
}

export const DATA_BLOCKS: Readonly<Record<string, FlowUiBlockRenderer>> = Object.freeze({
    data_table(block, ctx) {
        if (block.rows === null) {
            const fileId = text(ctx, block.file_id);
            if (fileId === null || fileId === '') return nothing;
            const file = fileById(ctx, fileId);
            if (file === null) return nothing;
            return fileCard(ctx, file);
        }
        const rows = valueAtPath(ctx.state, block.rows);
        if (rows === undefined || rows === null) return nothing;
        if (!Array.isArray(rows)) throw new Error(`flow-ui: data_table rows at ${block.rows} must be a list`);
        const rawColumns = declaredColumns(block.columns);
        const columns: { key: string; label: unknown }[] = rawColumns !== null && rawColumns.length > 0
            ? rawColumns.map((column) => ({ key: column.key, label: text(ctx, column.label) ?? column.key }))
            : inferredColumns(rows);
        const rowAction = rowActionOf(block.row_action);
        const clickable = rowAction !== null && !ctx.readonly;
        return html`<div class="fu-table-wrap"><table class="fu-table">
            <thead><tr>${columns.map((column) => html`<th>${column.label}</th>`)}</tr></thead>
            <tbody>${rows.map((row, index) => html`<tr data-row-index=${index} data-clickable=${clickable ? 'true' : nothing}
                @click=${clickable && rowAction !== null ? () => ctx.onAction(block, { name: rowAction.name, payload: actionPayload(rowAction.payload, row) }) : nothing}>
                ${columns.map((column) => html`<td>${cellText(cellValue(row, column.key))}</td>`)}
            </tr>`)}</tbody>
        </table></div>`;
    },

    chart(block, ctx) {
        const points = valueAtPath(ctx.state, block.data);
        if (points === undefined || points === null) return nothing;
        if (!Array.isArray(points)) throw new Error(`flow-ui: chart data at ${block.data} must be a list`);
        const title = shown(text(ctx, block.title));
        const chartX = typeof block.x === 'string' ? block.x : '';
        const chartYs = Array.isArray(block.y) ? block.y.map(String) : [];
        const firstSeries = chartYs[0];
        const chart = block.kind === 'pie' ? pieChart(points, chartX, firstSeries === undefined ? '' : firstSeries) : xyChart(String(block.kind), points, chartX, chartYs);
        return html`<figure class="fu-chart" data-kind=${block.kind}>
            ${title !== '' ? html`<figcaption class="title">${title}</figcaption>` : ''}
            ${chart.svg}
            <div class="legend">${chart.legend.map((item) => html`<span><i style=${`background:${item.color}`}></i>${item.label}</span>`)}</div>
        </figure>`;
    },

    json_view(block, ctx) {
        const value = valueAtPath(ctx.state, block.path);
        if (value === undefined) return nothing;
        const title = shown(text(ctx, block.title));
        return html`<div class="fu-card">
            ${title !== '' ? html`<div class="head">${title}</div>` : ''}
            <pre class="fu-json">${JSON.stringify(value, null, 2)}</pre>
        </div>`;
    },

    file_card(block, ctx) {
        if (block.file !== null) {
            const file = valueAtPath(ctx.state, block.file);
            if (file === undefined || file === null) return nothing;
            return fileCard(ctx, fileRecord(file));
        }
        const fileId = text(ctx, block.file_id);
        if (fileId === null || fileId === '') return nothing;
        const file = fileById(ctx, fileId);
        return file === null ? nothing : fileCard(ctx, file);
    },

    file_list(block, ctx) {
        const files = valueAtPath(ctx.state, block.files);
        if (files === undefined || files === null) return nothing;
        if (!Array.isArray(files)) throw new Error(`flow-ui: file_list at ${block.files} must be a list`);
        if (files.length === 0) return html`<div class="fu-empty"><strong>${flowUIText(ctx.locale, 'files_empty')}</strong></div>`;
        return html`<div class="fu-file-list">${files.map((file) => fileCard(ctx, file))}</div>`;
    },
});
