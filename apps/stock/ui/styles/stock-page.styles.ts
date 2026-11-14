/**
 * Каноничный каркас страниц stock-админки: `.wrap` с фиксированной шириной
 * и паддингами, `.toolbar` (поиск + фильтры одной высоты и радиуса),
 * `.table-card` + `table`, секционные заголовки.
 *
 * Все страницы используют `page-header` + эти стили — разнородные `h1`,
 * `.head` и собственные табличные правила запрещены.
 */

import { css } from 'lit';

export const stockPageStyles = css`
    :host { display: block; height: 100%; overflow-y: auto; }

    .wrap {
        max-width: 1100px;
        margin: 0 auto;
        padding: var(--space-6);
        box-sizing: border-box;
    }

    /* Тулбар: все контролы — pill одной высоты (modal-search-field канон). */
    .toolbar {
        display: flex;
        gap: var(--space-2);
        align-items: center;
        flex-wrap: wrap;
        margin-bottom: var(--space-4);
    }
    .toolbar platform-modal-search-field {
        flex: 1 1 220px;
        max-width: 360px;
    }
    .toolbar platform-searchable-combobox {
        --field-pill-compact-radius: var(--radius-full);
        min-width: 200px;
        max-width: 280px;
    }

    /* Карточка-остров под таблицу. */
    .table-card {
        border: 1px solid var(--glass-border-subtle);
        border-radius: var(--radius-lg);
        background: var(--glass-solid-subtle);
        overflow: hidden;
    }
    .table-card .scroll { overflow-x: auto; }
    .table-card platform-empty-state { margin: var(--space-6) 0; }

    table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
    th, td {
        padding: var(--space-2) var(--space-4);
        text-align: left;
        border-bottom: 1px solid var(--glass-border-subtle);
        color: var(--text-primary);
    }
    th {
        color: var(--text-tertiary);
        font-weight: var(--font-medium);
        font-size: var(--text-xs);
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    tbody tr:last-child td { border-bottom: none; }
    td.num, th.num, .num { text-align: right; font-variant-numeric: tabular-nums; }
    tr.clickable { cursor: pointer; }
    tr.clickable:hover td { background: var(--surface-2); }

    /* Секция внутри страницы (вторая таблица под основной). */
    .section {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: var(--space-3);
        margin: var(--space-6) 0 var(--space-3);
    }
    .section h2 {
        margin: 0;
        font-size: var(--text-lg);
        font-weight: var(--font-semibold);
        color: var(--text-primary);
    }

    .icon-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        border: none;
        border-radius: var(--radius-md);
        background: transparent;
        color: var(--text-tertiary);
        cursor: pointer;
        padding: 0;
    }
    .icon-btn:hover { background: var(--glass-tint-medium); color: var(--text-primary); }
    .icon-btn.danger:hover { color: var(--danger, #f87171); }

    @media (max-width: 767px) {
        .wrap { padding: var(--space-3); }
        .toolbar platform-modal-search-field { max-width: none; }
        .toolbar platform-searchable-combobox { max-width: none; flex: 1 1 100%; }
    }
`;
