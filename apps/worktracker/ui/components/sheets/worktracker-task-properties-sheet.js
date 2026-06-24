/**
 * WorktrackerTaskPropertiesSheet — mobile properties bottom sheet.
 *
 * kind: 'worktracker.task_properties'
 */

import { html, css } from 'lit';
import { PlatformBottomSheet } from '@platform/lib/components/layout/platform-bottom-sheet.js';
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';
import '../work-item-detail-editor.js';

export class WorktrackerTaskPropertiesSheet extends PlatformBottomSheet {
    static bottomSheetKind = 'worktracker.task_properties';
    static i18nNamespace = 'worktracker';

    static properties = {
        ...PlatformBottomSheet.properties,
        workItemId: { type: String, attribute: 'work-item-id' },
    };

    static styles = [
        PlatformBottomSheet.styles,
        css`
            worktracker-detail-inspector {
                display: block;
                width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this.workItemId = '';
        this.snap = 'full';
    }

    connectedCallback() {
        super.connectedCallback();
        this.heading = this.t('detail_page.section_properties');
    }

    renderBody() {
        if (typeof this.workItemId !== 'string' || this.workItemId.length === 0) {
            throw new Error('WorktrackerTaskPropertiesSheet: workItemId is required');
        }
        return html`
            <work-item-detail-editor
                layout="inspector-only"
                work-item-id=${this.workItemId}
                active
            ></work-item-detail-editor>
        `;
    }
}

customElements.define('worktracker-task-properties-sheet', WorktrackerTaskPropertiesSheet);
registerBottomSheetKind(
    WorktrackerTaskPropertiesSheet.bottomSheetKind,
    'worktracker-task-properties-sheet',
);
