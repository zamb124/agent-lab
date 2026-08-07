import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { conversationSessionFiles } from '../../../../core/frontend/static/lib/flow-ui/catalog/platform/conversation-turn.js';
import { openFlowUISessionFile } from '../../../../core/frontend/static/lib/flow-ui/utils/open-session-file.js';
import { FILES_EVENTS } from '../../../../core/frontend/static/lib/events/reducers/files.js';
import {
    setPlatformBus,
    resetPlatformBusForTests,
} from '../../../../core/frontend/static/lib/events/bus-singleton.js';
import { resolveFileIconKey } from '../../../../core/frontend/static/lib/utils/file-icons.js';

describe('conversationSessionFiles', () => {
    it('collects unique FileRefs from user_message artifacts across tasks', () => {
        const files = conversationSessionFiles([
            {
                id: 't1',
                status: { state: 'TASK_STATE_COMPLETED' },
                artifacts: [{
                    name: 'user_message',
                    parts: [
                        { text: 'что там' },
                        {
                            data: {
                                files: [{
                                    file_id: 'f1',
                                    original_name: 'IMG_2444.JPG',
                                    content_type: 'image/jpeg',
                                    file_size: 12,
                                }],
                            },
                        },
                    ],
                }],
            },
            {
                id: 't2',
                status: { state: 'TASK_STATE_COMPLETED' },
                artifacts: [{
                    name: 'user_message',
                    parts: [{
                        data: {
                            files: [
                                {
                                    file_id: 'f1',
                                    original_name: 'IMG_2444.JPG',
                                    url: '/flows/api/v1/files/f1/download',
                                },
                                {
                                    file_id: 'f2',
                                    original_name: 'notes.pdf',
                                },
                            ],
                        },
                    }],
                }],
            },
        ]);
        expect(files).toHaveLength(2);
        expect(files.map((item) => item.file_id).sort()).toEqual(['f1', 'f2']);
        const first = files.find((item) => item.file_id === 'f1');
        expect(first.url).toBe('/flows/api/v1/files/f1/download');
        expect(first.content_type).toBe('image/jpeg');
    });

    it('includes A2A file parts with metadata.file_id', () => {
        const files = conversationSessionFiles([{
            id: 't1',
            status: { state: 'TASK_STATE_COMPLETED' },
            history: [],
            artifacts: [{
                name: 'response',
                parts: [{
                    file: { name: 'out.csv', uri: '/x' },
                    metadata: { file_id: 'csv-1' },
                    mediaType: 'text/csv',
                }],
            }],
        }]);
        expect(files).toEqual([{
            file_id: 'csv-1',
            original_name: 'out.csv',
            content_type: 'text/csv',
            url: '/x',
        }]);
    });

    it('maps session image names to core file icon keys (not download thumbnails)', () => {
        expect(resolveFileIconKey('icon-144x144.png', 'image/png')).toBe('image');
        expect(resolveFileIconKey('IMG_2444.JPG', 'image/jpeg')).toBe('image');
        expect(resolveFileIconKey('notes.pdf', 'application/pdf')).toBe('pdf');
    });
});

describe('openFlowUISessionFile', () => {
    beforeEach(() => {
        resetPlatformBusForTests();
    });
    afterEach(() => {
        resetPlatformBusForTests();
        vi.restoreAllMocks();
    });

    it('dispatches files/file/open_requested on platform bus', () => {
        const dispatched = [];
        vi.stubGlobal('window', {});
        setPlatformBus({
            dispatch(type, payload) {
                dispatched.push({ type, payload });
            },
        });
        openFlowUISessionFile(
            { file_id: 'f-doc', original_name: 'doc.pdf', content_type: 'application/pdf' },
            'flow_ui_bubble',
        );
        expect(dispatched).toHaveLength(1);
        expect(dispatched[0].type).toBe(FILES_EVENTS.OPEN_REQUESTED);
        expect(dispatched[0].payload.file.file_id).toBe('f-doc');
        expect(dispatched[0].payload.source).toBe('flow_ui_bubble');
    });
    it('opens download URL when bus is absent', () => {
        const open = vi.fn();
        vi.stubGlobal('window', { open, location: { pathname: '/flows/chat' } });
        openFlowUISessionFile({
            file_id: 'f-img',
            original_name: 'a.jpg',
            url: '/flows/api/v1/files/f-img/download',
        });
        expect(open).toHaveBeenCalledWith(
            '/flows/api/v1/files/f-img/download',
            '_blank',
            'noopener',
        );
    });
});
