/**
 * Ручки ширины и кнопки align на рамке выделения. Геометрия — ``span-layout.js``.
 */

import { html, nothing } from '../../lit-shim.js';
import { ALIGN_VALUES, blockAlign, blockSpan, spanContainerWidth, startSpanResize } from './span-layout.js';

export { ALIGN_VALUES, SPAN_COLUMNS, blockAlign, blockSpan, clampSpan, spanFromPointer, spanContainerWidth, startSpanResize } from './span-layout.js';

export function renderAlignButtons({ block, t, setProperty }) {
    if (!block || block.type === 'conversation') return nothing;
    const current = blockAlign(block);
    return html`<div class="align" role="group" aria-label=${t('interface_editor.prop_align')}>
        ${ALIGN_VALUES.map((value) => html`<button type="button" data-align=${value}
            aria-pressed=${current === value ? 'true' : 'false'}
            aria-label=${t(`interface_editor.align_${value}`)}
            @click=${(event) => { event.stopPropagation(); setProperty(block.block_id, 'align', value); }}></button>`)}
    </div>`;
}

export function renderSpanHandle({ block, t, setProperty, blockEl }) {
    if (!block || block.type === 'conversation') return nothing;
    return html`<div class="resize-e" title=${t('interface_editor.resize_span')}
        @pointerdown=${(event) => {
            event.preventDefault();
            event.stopPropagation();
            startSpanResize({
                event,
                startSpan: blockSpan(block),
                containerWidth: spanContainerWidth(blockEl),
                onSpan: (span) => setProperty(block.block_id, 'span', span),
            });
        }}></div>`;
}
