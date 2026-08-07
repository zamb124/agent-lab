import { describe, expect, it } from 'vitest';

import { projectA2AArtifact, projectA2APart } from '../../../../core/frontend/static/lib/flow-ui/protocol/generic-part-projector.js';

describe('generic-part-projector', () => {
    it('projects text/raw/url/data parts without loss', () => {
        expect(projectA2APart({ text: 'hello' })).toMatchObject({
            kind: 'text', text: 'hello',
        });
        expect(projectA2APart({ raw: 'YmFzZTY0', mediaType: 'image/png' })).toMatchObject({
            kind: 'raw', raw: 'YmFzZTY0', mediaType: 'image/png',
        });
        expect(projectA2APart({
            url: 'https://files.example/a.bin',
            filename: 'a.bin',
            mediaType: 'application/octet-stream',
        })).toMatchObject({
            kind: 'file',
            url: 'https://files.example/a.bin',
            filename: 'a.bin',
        });
        expect(projectA2APart({ data: { flowUi: { revision: 2 } } })).toMatchObject({
            kind: 'data',
            data: { flowUi: { revision: 2 } },
        });
    });

    it('projects mixed artifact parts in order', () => {
        const projected = projectA2AArtifact({
            artifactId: 'mixed-1',
            name: 'mixed',
            parts: [
                { text: 'caption' },
                { data: { rows: [1, 2] } },
                { url: '/files/x', filename: 'x', mediaType: 'text/plain' },
            ],
        });
        expect(projected.artifactId).toBe('mixed-1');
        expect(projected.parts.map((part) => part.kind)).toEqual(['text', 'data', 'file']);
    });
});
