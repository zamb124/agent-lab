/**
 * platform-segmented-control — pill segmented selector smoke tests.
 */

import { fixture, html, expect, oneEvent } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-segmented-control.js';
import { qs, qsa, shadow, type TestEl } from '../helpers/dom.js';

describe('platform-segmented-control', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('renders items and marks active segment', async () => {
        const el = await fixture<TestEl>(html`
            <platform-segmented-control
                value="run"
                .items=${[
                    { value: 'edit', icon: 'edit', title: 'Edit' },
                    { value: 'run', icon: 'play', title: 'Run' },
                ]}
                icon-only
                density="dense"
            ></platform-segmented-control>
        `);
        const active = qs(shadow(el), '.segment[data-active="true"]');
        expect(active).to.exist;
        expect(active.getAttribute('aria-pressed')).to.equal('true');
    });

    it('emits change with selected value', async () => {
        const el = await fixture<TestEl>(html`
            <platform-segmented-control
                value="edit"
                .items=${[
                    { value: 'edit', label: 'Edit' },
                    { value: 'run', label: 'Run' },
                ]}
            ></platform-segmented-control>
        `);
        const segments = qsa(shadow(el), '.segment');
        setTimeout(() => segments[1]!.click());
        const ev = await oneEvent(el, 'change');
        expect((ev as CustomEvent).detail.value).to.equal('run');
    });

    it('emits segment-close for closable items', async () => {
        const el = await fixture<TestEl>(html`
            <platform-segmented-control
                value="b1"
                .items=${[
                    { value: 'base', label: 'Base' },
                    { value: 'b1', label: 'Branch 1', closable: true },
                ]}
            ></platform-segmented-control>
        `);
        const closeBtn = qs(shadow(el), '.segment-close');
        expect(closeBtn).to.exist;
        setTimeout(() => (closeBtn as TestEl).click());
        const ev = await oneEvent(el, 'segment-close');
        expect((ev as CustomEvent).detail.value).to.equal('b1');
    });

    it('passes colored to brand platform-icon', async () => {
        const el = await fixture<TestEl>(html`
            <platform-segmented-control
                value="javascript"
                icon-only
                .items=${[
                    { value: 'python', icon: 'python', colored: true, title: 'Python' },
                    { value: 'javascript', icon: 'javascript', colored: true, title: 'JavaScript' },
                ]}
            ></platform-segmented-control>
        `);
        const icons = qsa(shadow(el), 'platform-icon');
        expect(icons.length).to.equal(2);
        expect(icons[0]!.hasAttribute('colored')).to.equal(true);
        expect(icons[1]!.hasAttribute('colored')).to.equal(true);
    });

    it('renders iconSrc as img and falls back on error', async () => {
        const el = await fixture<TestEl>(html`
            <platform-segmented-control
                value="javascript"
                icon-only
                .items=${[
                    {
                        value: 'javascript',
                        iconSrc: '/static/core/assets/icons/javascript.svg',
                        iconFallback: 'JS',
                        title: 'JavaScript',
                    },
                    {
                        value: 'broken',
                        iconSrc: '/static/core/assets/icons/__missing_language_icon__.svg',
                        iconFallback: 'XX',
                        title: 'Broken',
                    },
                ]}
            ></platform-segmented-control>
        `);
        expect(qsa(shadow(el), 'platform-icon').length).to.equal(0);
        const images = qsa(shadow(el), 'img.segment-icon-img');
        expect(images.length).to.be.at.least(1);
        expect(images[0]!.getAttribute('src')).to.equal('/static/core/assets/icons/javascript.svg');

        const brokenImg = [...images].find(
            (img) => img.getAttribute('src') === '/static/core/assets/icons/__missing_language_icon__.svg',
        );
        expect(brokenImg).to.exist;
        brokenImg!.dispatchEvent(new Event('error'))!;
        await el.updateComplete;
        const fallback = qs(shadow(el), '.segment-icon-fallback');
        expect(fallback).to.exist;
        expect(fallback.textContent).to.equal('XX');
    });

    it('uses renderIcon instead of platform-icon when provided', async () => {
        const el = await fixture<TestEl>(html`
            <platform-segmented-control
                value="a"
                icon-only
                .items=${[
                    { value: 'a', title: 'A' },
                    { value: 'b', title: 'B' },
                ]}
                .renderIcon=${(item: any) => html`<span class="custom-icon" data-value=${(item as TestEl).value}>${(item as TestEl).value}</span>`}
            ></platform-segmented-control>
        `);
        expect(qsa(shadow(el), 'platform-icon').length).to.equal(0);
        const custom = qsa(shadow(el), '.custom-icon');
        expect(custom.length).to.equal(2);
        expect(custom[0]!.getAttribute('data-value')).to.equal('a');
    });
});
