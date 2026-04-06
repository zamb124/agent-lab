import { LitElement, html, css } from 'lit';

export class EmbedUiTable extends LitElement {
    static properties = {
        columns: { type: Array },
        rows: { type: Array },
    };

    static styles = css`
        :host {
            display: block;
            overflow-x: auto;
            --embed-table-text: var(--embed-chat-text, rgba(255, 255, 255, 0.92));
            --embed-table-border: var(--embed-chat-border, rgba(255, 255, 255, 0.12));
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            color: var(--embed-table-text);
        }
        th,
        td {
            border: 1px solid var(--embed-table-border);
            padding: 8px 10px;
            text-align: left;
        }
        th {
            font-weight: 600;
            background: var(--embed-chat-surface, rgba(255, 255, 255, 0.04));
        }
    `;

    render() {
        const cols = Array.isArray(this.columns) ? this.columns : [];
        const rows = Array.isArray(this.rows) ? this.rows : [];
        return html`
            <table>
                <thead>
                    <tr>
                        ${cols.map((c) => html`<th>${typeof c === 'string' ? c : c.label || c.key || ''}</th>`)}
                    </tr>
                </thead>
                <tbody>
                    ${rows.map(
                        (row) => html`
                            <tr>
                                ${cols.map((c) => {
                                    const key = typeof c === 'string' ? c : c.key;
                                    const val = row && key != null ? row[key] : '';
                                    return html`<td>${val ?? ''}</td>`;
                                })}
                            </tr>
                        `,
                    )}
                </tbody>
            </table>
        `;
    }
}

customElements.define('embed-ui-table', EmbedUiTable);
