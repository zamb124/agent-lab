import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { notesListResource } from '../../../../apps/crm/ui/events/resources/notes.resource.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

beforeEach(() => {
    resetFactories();
});

afterEach(() => {
    resetFactories();
});

describe('crm/notes_list push merge', () => {
    it('merges note snapshot into items on crm/note/updated', () => {
        const state = {
            items: [
                {
                    entity_id: 'note_1',
                    namespace: 'default',
                    entity_subtype: 'meeting',
                    note_date: '2026-07-20',
                    name: 'Old',
                },
            ],
            filters: {
                namespace: 'default',
                date_from: '2026-07-01',
                date_to: '2026-07-31',
            },
            loading: false,
            error: null,
            nextCursor: null,
            hasMore: false,
        };
        const next = notesListResource.reducer(state, {
            type: 'crm/note/updated',
            payload: {
                note_id: 'note_1',
                action: 'updated',
                note: {
                    entity_id: 'note_1',
                    namespace: 'default',
                    entity_subtype: 'meeting',
                    note_date: '2026-07-20',
                    name: 'New title',
                },
            },
        });
        expect(next.items).toHaveLength(1);
        expect(next.items[0].name).toBe('New title');
    });

    it('removes note on deleted action', () => {
        const state = {
            items: [
                { entity_id: 'note_1', namespace: 'default', note_date: '2026-07-20', name: 'A' },
                { entity_id: 'note_2', namespace: 'default', note_date: '2026-07-21', name: 'B' },
            ],
            filters: { namespace: 'default' },
            loading: false,
            error: null,
            nextCursor: null,
            hasMore: false,
        };
        const next = notesListResource.reducer(state, {
            type: 'crm/note/updated',
            payload: {
                note_id: 'note_1',
                action: 'deleted',
            },
        });
        expect(next.items.map((item) => item.entity_id)).toEqual(['note_2']);
    });

    it('ignores markdown started/partial without touching items', () => {
        const state = {
            items: [{ entity_id: 'note_1', namespace: 'default', note_date: '2026-07-20', name: 'A' }],
            filters: { namespace: 'default' },
            loading: false,
            error: null,
            nextCursor: null,
            hasMore: false,
        };
        const next = notesListResource.reducer(state, {
            type: 'crm/note/updated',
            payload: {
                note_id: 'note_1',
                action: 'updated',
                markdown_format: { phase: 'started', chunks_done: 0, chunks_total: 0 },
                note: {
                    entity_id: 'note_1',
                    namespace: 'default',
                    note_date: '2026-07-20',
                    name: 'Changed',
                },
            },
        });
        expect(next).toBe(state);
    });
});
