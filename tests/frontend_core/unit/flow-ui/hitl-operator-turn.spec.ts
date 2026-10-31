import { describe, expect, it } from 'vitest';

import { operatorTurnFromAction } from '../../../../core/frontend/static/lib/flow-ui/runtime/hitl-transport.js';

const inputBlocks = [
    { type: 'text_input', block_id: 'note', field: 'message', label: 'Reply' },
    { type: 'checkbox', block_id: 'urgent', field: 'urgent', label: 'Urgent' },
    { type: 'select', block_id: 'tags', field: 'tags', label: 'Tags {customer.name}' },
    { type: 'file_upload', block_id: 'docs', field: 'attachments', label: 'Documents' },
];

describe('operatorTurnFromAction', () => {
    it('projects fields to labelled lines in page order and passes files as attachments', () => {
        const attachment = {
            file_id: 'f1', original_name: 'scan.pdf', content_type: 'application/pdf', file_size: 10, url: null,
        };
        const turn = operatorTurnFromAction(
            { name: 'submit' },
            { tags: ['vip', 'late'], message: 'On my way', urgent: true, attachments: [attachment] },
            inputBlocks,
            'en',
        );
        expect(turn.text).toBe('Reply: On my way\nUrgent: yes\ntags: vip, late');
        expect(turn.files).toEqual([attachment]);
    });

    it('localizes booleans and skips fields that were not submitted', () => {
        const turn = operatorTurnFromAction({ name: 'submit' }, { urgent: false }, inputBlocks, 'ru');
        expect(turn.text).toBe('Urgent: нет');
        expect(turn.files).toEqual([]);
    });

    it('sends the action name when the page has no submitted fields', () => {
        expect(operatorTurnFromAction({ name: 'approve' }, {}, inputBlocks, 'en')).toEqual({ text: 'approve', files: [] });
    });

    it('requires an action name', () => {
        expect(() => operatorTurnFromAction({}, {}, inputBlocks, 'en')).toThrow(/requires name/);
    });
});
