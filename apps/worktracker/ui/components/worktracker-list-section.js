/**
 * WorktrackerListSection — section title with count + list slot.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { worktrackerSurfacesStyles } from '../styles/worktracker-surfaces.styles.js';
import { worktrackerListStyles } from '../styles/worktracker-list.styles.js';

export class WorktrackerListSection extends PlatformElement {
    static properties = {
        title: { type: String },
        count: { type: Number },
    };

    static styles = [
        PlatformElement.styles,
        worktrackerSurfacesStyles,
        worktrackerListStyles,
        css`
            :host {
                display: block;
                min-width: 0;
            }
        `,
    ];

    constructor() {
        super();
        this.title = '';
        this.count = 0;
    }

    _titleText() {
        const base = typeof this.title === 'string' ? this.title : '';
        if (typeof this.count === 'number' && this.count > 0) {
            return `${base} (${this.count})`;
        }
        return base;
    }

    render() {
        return html`
            <section class="wt-section">
                <h2 class="wt-section-title">${this._titleText()}</h2>
                <div class="wt-list">
                    <slot></slot>
                </div>
            </section>
        `;
    }
}

customElements.define('worktracker-list-section', WorktrackerListSection);
