import { describe, it, expect } from 'vitest';
import { blocksFromToolResult } from '../../../../core/frontend/static/lib/chat/tool-result-blocks.js';

describe('flows-chat tool result blocks', () => {
    it('promotes document tool result files to shared file_card blocks', () => {
        const blocks = blocksFromToolResult({
            id: 'tc-doc',
            name: 'documents_open_file',
            result: JSON.stringify({
                success: true,
                file: {
                    file_id: 'file-docx-1',
                    original_name: 'Contract.docx',
                    content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    url: '/frontend/api/v1/files/download/file-docx-1',
                },
                document: {
                    binding_id: 'binding-docx-1',
                    file_id: 'file-docx-1',
                    editor_url: '/documents/embed/edit/binding-docx-1?namespace=system',
                    namespace: 'system',
                },
            }),
        });

        expect(blocks).toEqual([{
            type: 'file_card',
            file_id: 'file-docx-1',
            name: 'Contract.docx',
            mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            file_size: undefined,
            url: '/frontend/api/v1/files/download/file-docx-1',
            preview_url: undefined,
            editor_url: '/documents/embed/edit/binding-docx-1?namespace=system',
            binding_id: 'binding-docx-1',
            catalog_id: undefined,
            document_type: undefined,
            namespace: 'system',
            document: {
                binding_id: 'binding-docx-1',
                file_id: 'file-docx-1',
                editor_url: '/documents/embed/edit/binding-docx-1?namespace=system',
                namespace: 'system',
            },
            capabilities: {
                document: {
                    binding_id: 'binding-docx-1',
                    file_id: 'file-docx-1',
                    editor_url: '/documents/embed/edit/binding-docx-1?namespace=system',
                    namespace: 'system',
                },
            },
        }]);
    });

    it('keeps create_viz blocks type=viz for inline chat preview', () => {
        const blocks = blocksFromToolResult({
            id: 'tc-viz',
            name: 'create_viz',
            result: JSON.stringify({
                success: true,
                files: [{
                    file_id: 'file-viz-1',
                    original_name: 'funnel.viz',
                    content_type: 'application/vnd.platform.viz+json',
                }],
                blocks: [{
                    type: 'viz',
                    file_id: 'file-viz-1',
                    kind: 'flowchart',
                    engine: 'mermaid',
                    title: 'Funnel',
                    spec: { source: 'flowchart TD\n  A-->B' },
                }],
            }),
        });

        expect(blocks).toEqual([{
            type: 'viz',
            file_id: 'file-viz-1',
            kind: 'flowchart',
            engine: 'mermaid',
            title: 'Funnel',
            spec: { source: 'flowchart TD\n  A-->B' },
        }]);
    });

    it('keeps update_viz and viz_open_file blocks type=viz', () => {
        for (const name of ['update_viz', 'viz_open_file']) {
            const blocks = blocksFromToolResult({
                id: `tc-${name}`,
                name,
                result: JSON.stringify({
                    success: true,
                    files: [{
                        file_id: 'file-viz-2',
                        original_name: 'updated.viz',
                        content_type: 'application/vnd.platform.viz+json',
                    }],
                    blocks: [{
                        type: 'viz',
                        file_id: 'file-viz-2',
                        kind: 'chart',
                        engine: 'echarts',
                        title: 'Updated',
                        spec: { option: { series: [] } },
                    }],
                }),
            });
            expect(blocks).toEqual([{
                type: 'viz',
                file_id: 'file-viz-2',
                kind: 'chart',
                engine: 'echarts',
                title: 'Updated',
                spec: { option: { series: [] } },
            }]);
        }
    });

    it('maps export_viz files[] to file_card when blocks are absent', () => {
        const blocks = blocksFromToolResult({
            id: 'tc-export-viz',
            name: 'export_viz',
            result: JSON.stringify({
                success: true,
                format: 'svg',
                source_file_id: 'file-viz-1',
                files: [{
                    file_id: 'file-svg-1',
                    original_name: 'funnel.svg',
                    content_type: 'image/svg+xml',
                    url: '/frontend/api/v1/files/download/file-svg-1',
                }],
            }),
        });

        expect(blocks).toEqual([{
            type: 'file_card',
            file_id: 'file-svg-1',
            name: 'funnel.svg',
            mime_type: 'image/svg+xml',
            file_size: undefined,
            url: '/frontend/api/v1/files/download/file-svg-1',
            preview_url: undefined,
            editor_url: '',
            binding_id: undefined,
            catalog_id: undefined,
            document_type: undefined,
            namespace: undefined,
            document: null,
            capabilities: {},
        }]);
    });
});
