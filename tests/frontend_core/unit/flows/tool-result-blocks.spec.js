import { describe, it, expect } from 'vitest';
import { blocksFromToolResult } from '../../../../core/frontend/static/lib/flows-chat/tool-result-blocks.js';

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
});
