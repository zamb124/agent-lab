/** Превью для строки списка каналов по payload сообщения (как на сервере). */
import { t } from '@platform/services/i18n/i18n.service.js';

const PREVIEW_MAX = 120;

/**
 * @param {object} p — payload message.created / MessageRead.
 * @returns {string|null}
 */
export function lanePreviewFromMessagePayload(p) {
    if (!p || typeof p !== 'object') {
        throw new Error(t('lane_preview.err_payload', {}));
    }
    const contents = p.contents;
    if (!Array.isArray(contents) || contents.length === 0) {
        return null;
    }
    const sorted = [...contents].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    const block = sorted[0];
    const blockType = block.type;
    const d = block.data;
    if (blockType === 'text/plain') {
        if (typeof d?.body !== 'string') {
            throw new Error(t('lane_preview.err_plain_body', {}));
        }
        const raw = d.body.trim();
        if (raw === '') {
            return '';
        }
        if (raw.length <= PREVIEW_MAX) {
            return raw;
        }
        return `${raw.slice(0, PREVIEW_MAX - 1)}…`;
    }
    if (blockType === 'code/block') {
        return t('lane_preview.code', {});
    }
    if (blockType === 'mock/image') {
        return t('lane_preview.image', {});
    }
    if (blockType === 'file/image') {
        return t('lane_preview.photo', {});
    }
    if (blockType === 'file/document') {
        return t('lane_preview.file', {});
    }
    if (blockType === 'file/audio') {
        return t('lane_preview.audio', {});
    }
    if (blockType === 'file/video') {
        return t('lane_preview.video', {});
    }
    if (blockType === 'call/boundary') {
        return t('lane_preview.call_boundary', {});
    }
    if (blockType === 'git/reference') {
        return t('lane_preview.git', {});
    }
    if (blockType === 'custom_tool_response') {
        return t('lane_preview.tool', {});
    }
    throw new Error(t('lane_preview.err_unknown_type', { type: blockType }));
}
