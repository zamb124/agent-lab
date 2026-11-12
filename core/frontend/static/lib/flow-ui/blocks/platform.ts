/**
 * Платформенные блоки: conversation, slot, agent_identity, avatar, run_trace, tool_activity,
 * browser_preview, skill_activity, action_preview, action_result, reflection, activity, agent_plan.
 */

import { html, nothing } from 'lit';
import { flowUIMediaSrc, resolveAgentIdentityImageSrc } from '../runtime/agent-identity-image.js';
import { taskActivity } from '../runtime/conversation.js';
import { blockText as text, blockUrl } from '../runtime/templating.js';
import { flowUIGlyph } from '../utils/glyph.js';
import { flowUIText } from '../utils/text.js';
import type { FlowUiBlockRenderer } from '../runtime/flow-ui-store.js';


import type { FlowUiActivityItem } from '../runtime/conversation.js';

function shown(value: string | null): string {
    return value === null ? '' : value;
}

function initials(name: string): string {
    return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => {
        const letter = part[0];
        if (letter === undefined) {
            throw new Error('flow-ui: avatar initial missing');
        }
        return letter.toUpperCase();
    }).join('');
}

export function activityChips(items: readonly FlowUiActivityItem[]) {
    return html`<div class="fu-chips">${items.map((item) => html`<span class="fu-chip" data-status=${item.status} data-kind=${item.kind} title=${item.detail}>
        ${item.label}${item.detail !== '' ? html`<span class="detail">${item.detail}</span>` : ''}
    </span>`)}</div>`;
}

function statusTone(status: unknown): 'danger' | 'success' | 'info' {
    if (status === 'failed' || status === 'error') return 'danger';
    if (status === 'success' || status === 'completed' || status === 'finished' || status === 'loaded') return 'success';
    return 'info';
}

export const PLATFORM_BLOCKS: Readonly<Record<string, FlowUiBlockRenderer>> = Object.freeze({
    conversation(block, ctx) {
        return html`<flow-ui-conversation ?editing=${ctx.editing === true} .host=${ctx.host} .settings=${block.settings} .blockId=${block.block_id}></flow-ui-conversation>`;
    },

    slot(block, ctx) {
        const title = shown(text(ctx, block.title));
        const blocks = ctx.slots[String(block.block_id)];
        const filled = Array.isArray(blocks) && blocks.length > 0;
        if (!filled && !ctx.editing) return title === '' ? nothing : html`<div class="fu-slot"><div class="title">${title}</div></div>`;
        return html`<div class="fu-slot" data-slot-id=${block.block_id}>
            ${title !== '' ? html`<div class="title">${title}</div>` : ''}
            ${filled ? ctx.renderBlocks?.(blocks) : html`<div class="fu-slot-empty">${flowUIText(ctx.locale, 'slot_empty')}</div>`}
        </div>`;
    },

    agent_identity(block, ctx) {
        const fromBlock = shown(text(ctx, block.title));
        const fromFlow = typeof ctx.flowIdentity?.title === 'string' ? ctx.flowIdentity.title.trim() : '';
        const title = fromBlock !== '' ? fromBlock : fromFlow;
        const src = resolveAgentIdentityImageSrc({
            imageUrl: typeof block.image_url === 'string' ? block.image_url : null,
            flowIdentity: ctx.flowIdentity,
            platformUiOrigin: ctx.platformUiOrigin,
        });
        return html`<div class="fu-identity"><img src=${src} alt="">${title !== '' ? html`<span class="title">${title}</span>` : ''}</div>`;
    },

    avatar(block, ctx) {
        const name = text(ctx, block.name);
        if (name === null) return nothing;
        const imageUrl = shown(blockUrl(ctx, block.image_url));
        return html`<span class="fu-avatar">
            ${imageUrl !== '' ? html`<img src=${flowUIMediaSrc(ctx.platformUiOrigin, imageUrl)} alt="">` : html`<span class="initials">${initials(name)}</span>`}
            <span>${name}</span>
        </span>`;
    },

    run_trace(block, ctx) {
        return html`<flow-ui-run-trace .tasks=${ctx.store.orderedTasks()} .locale=${ctx.locale}></flow-ui-run-trace>`;
    },

    tool_activity(block, ctx) {
        const task = ctx.store.task(ctx.store.activeTaskId);
        if (!task) return ctx.editing ? html`<div class="fu-slot-empty">${flowUIText(ctx.locale, 'tool_activity_empty')}</div>` : nothing;
        const items = taskActivity(task, { show_activity: true, tool_calls: typeof block.display === 'string' ? block.display : undefined, show_skill_loads: true, errors: 'detailed' }, ctx.locale);
        return items.length === 0 ? nothing : activityChips(items);
    },

    browser_preview(block, ctx) {
        const url = blockUrl(ctx, block.url);
        if (url === null || url === '') return nothing;
        const title = shown(text(ctx, block.title));
        const screenshot = shown(blockUrl(ctx, block.screenshot_url));
        return html`<div class="fu-card fu-preview" data-status=${block.status}>
            <div class="head"><span>${title !== '' ? title : url}</span><span class="fu-status" data-tone=${statusTone(block.status)}>${flowUIText(ctx.locale, `browser_status_${block.status}`)}</span></div>
            ${screenshot !== '' ? html`<img src=${flowUIMediaSrc(ctx.platformUiOrigin, screenshot)} alt="" loading="lazy"
                style="cursor:zoom-in" @click=${() => ctx.host.openBrowserPreview({ url, title, status: block.status })}
                @error=${(event: Event) => { (event.target as HTMLImageElement).style.display = 'none'; }}>` : ''}
        </div>`;
    },

    skill_activity(block, ctx) {
        const title = text(ctx, block.title);
        if (title === null) return nothing;
        const status = block.status === 'loading' ? 'running' : (block.status === 'failed' ? 'error' : 'done');
        return html`<div class="fu-chips"><span class="fu-chip" data-kind="skill" data-status=${status} data-agent-skill-id=${block.agent_skill_id}>
            ${flowUIText(ctx.locale, 'skill_label')}: ${title}
        </span></div>`;
    },

    action_preview(block, ctx) {
        const title = text(ctx, block.title);
        const summary = text(ctx, block.summary);
        if (title === null || summary === null) return nothing;
        const entries = Object.entries(block.parameters && typeof block.parameters === 'object' ? block.parameters : {});
        return html`<div class="fu-card" data-card="action_preview">
            <div class="head"><span>${title}</span><span class="fu-badge" data-tone="info">${flowUIText(ctx.locale, 'action_preview_label')}</span></div>
            ${summary !== '' ? html`<p>${summary}</p>` : ''}
            ${entries.length > 0 ? html`<dl>${entries.map(([key, value]) => html`<dt>${key}</dt><dd>${typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd>`)}</dl>` : ''}
        </div>`;
    },

    action_result(block, ctx) {
        const title = text(ctx, block.title);
        const summary = text(ctx, block.summary);
        if (title === null || summary === null) return nothing;
        return html`<div class="fu-card" data-card="action_result" data-status=${block.status}>
            <div class="head"><span>${title}</span><span class="fu-status" data-tone=${statusTone(block.status)}>${flowUIText(ctx.locale, `action_status_${block.status}`)}</span></div>
            ${summary !== '' ? html`<p>${summary}</p>` : ''}
        </div>`;
    },

    reflection(block, ctx) {
        const value = text(ctx, block.text);
        if (value === null || value === '') return nothing;
        const tone = block.tone === 'warning' || block.tone === 'error' ? block.tone : 'success';
        const detail = typeof block.detail === 'string' ? text(ctx, block.detail) : null;
        return html`<div class="fu-reflection" data-tone=${tone}>
            <div class="fu-reflection-verdict">${value}</div>
            ${detail !== null && detail !== '' ? html`<div class="reflection-detail">${detail}</div>` : nothing}
        </div>`;
    },

    agent_plan(block) {
        return html`<platform-agent-plan .plan=${block.plan}></platform-agent-plan>`;
    },

    activity(block, ctx) {
        const title = text(ctx, block.title);
        const detail = text(ctx, block.detail);
        if (title === null || detail === null) return nothing;
        const status = block.status === 'running' ? 'running' : (block.status === 'failed' ? 'error' : 'done');
        return html`<div class="fu-chips"><span class="fu-chip" data-kind="activity" data-status=${status}>
            ${status === 'error' ? flowUIGlyph('alert-triangle', 12, ctx.platformUiOrigin) : ''}
            ${title}${detail !== '' ? html`<span class="detail">${detail}</span>` : ''}
        </span></div>`;
    },
});
