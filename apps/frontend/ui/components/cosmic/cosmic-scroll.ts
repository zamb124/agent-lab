/**
 * CosmicScrollController — хореография скролла космических страниц.
 *
 * Lenis-инерция (ленивый чанк, выключен при prefers-reduced-motion; touch —
 * нативный скролл, Lenis его не сглаживает), rAF-петля: глобальный прогресс →
 * `cosmic-scene` и `cosmic-rail`, активная глава по геометрии
 * `[data-cosmic-chapter]` секций (hue + label → сцена, номер → рельса),
 * `[data-cosmic-pin]` секции получают `--cosmic-section-t` (0..1) для
 * sticky-траверсов внутри теневых деревьев (custom property пробивает shadow).
 *
 * Якорная навигация — через `scrollToSection` (Lenis scrollTo, без Lenis —
 * нативный instant scrollIntoView).
 */
import type Lenis from 'lenis';
import type { CosmicScene } from './cosmic-scene.js';
import type { CosmicRail } from './cosmic-rail.js';

interface ChapterSection {
    el: HTMLElement;
    top: number;
    bottom: number;
    hue: number;
    label: string;
    pin: boolean;
}

export class CosmicScrollController {
    private _root: HTMLElement;
    private _scene: CosmicScene;
    private _rail: CosmicRail;
    private _lenis: Lenis | null = null;
    private _chapters: ChapterSection[] = [];
    private _resizeObserver: ResizeObserver | null = null;
    private _mutationObserver: MutationObserver | null = null;
    private _raf = 0;
    private _running = false;
    private _reduced = false;
    private _activeChapter = -1;

    constructor(root: HTMLElement, scene: CosmicScene, rail: CosmicRail) {
        this._root = root;
        this._scene = scene;
        this._rail = rail;
    }

    get reducedMotion(): boolean {
        return this._reduced;
    }

    async start(): Promise<void> {
        this._reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (!this._reduced) {
            const { default: LenisCtor } = await import('lenis');
            this._lenis = new LenisCtor({
                lerp: 0.09,
                smoothWheel: true,
                wheelMultiplier: 1,
            });
        }
        this._collectChapters();
        this._resizeObserver = new ResizeObserver(() => this._collectChapters());
        this._resizeObserver.observe(this._root);
        /* i18n-бандл может догрузиться после первого collect — лейблы глав
           перечитываем по смене атрибутов. */
        this._mutationObserver = new MutationObserver(() => this._collectChapters());
        this._mutationObserver.observe(this._root, {
            attributes: true,
            attributeFilter: ['data-cosmic-label', 'data-cosmic-hue'],
            subtree: true,
        });
        this._running = true;
        this._raf = requestAnimationFrame(this._frame);
    }

    stop(): void {
        this._running = false;
        cancelAnimationFrame(this._raf);
        if (this._lenis !== null) {
            this._lenis.destroy();
            this._lenis = null;
        }
        if (this._resizeObserver !== null) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
        if (this._mutationObserver !== null) {
            this._mutationObserver.disconnect();
            this._mutationObserver = null;
        }
        this._chapters = [];
    }

    scrollToSection(target: HTMLElement): void {
        if (this._lenis !== null) {
            this._lenis.scrollTo(target, { offset: -72, duration: 1.4 });
            return;
        }
        const top = target.getBoundingClientRect().top + window.scrollY - 72;
        window.scrollTo({ top, behavior: this._reduced ? 'instant' : 'smooth' });
    }

    private _collectChapters(): void {
        const scrollY = window.scrollY;
        const found: ChapterSection[] = [];
        this._root.querySelectorAll<HTMLElement>('[data-cosmic-chapter]').forEach((el) => {
            const rect = el.getBoundingClientRect();
            const hueRaw = el.getAttribute('data-cosmic-hue');
            const label = el.getAttribute('data-cosmic-label');
            found.push({
                el,
                top: rect.top + scrollY,
                bottom: rect.bottom + scrollY,
                hue: hueRaw === null ? 0.56 : Number(hueRaw),
                label: label === null ? '' : label,
                pin: el.hasAttribute('data-cosmic-pin'),
            });
        });
        this._chapters = found;
        this._rail.chapterCount = found.length;
        this._activeChapter = -1;
    }

    private _frame = (time: number): void => {
        if (!this._running) {
            return;
        }
        if (this._lenis !== null) {
            this._lenis.raf(time);
        }
        const vh = window.innerHeight;
        const scrollY = window.scrollY;
        const doc = Math.max(1, this._root.scrollHeight - vh);
        const progress = Math.min(1, Math.max(0, scrollY / doc));

        this._scene.progress = progress;
        this._rail.progress = progress;

        let activeIndex = -1;
        const probe = scrollY + vh * 0.45;
        this._chapters.forEach((chapter, index) => {
            if (chapter.pin) {
                const pinRange = Math.max(1, chapter.bottom - chapter.top - vh);
                const t = Math.min(1, Math.max(0, (scrollY - chapter.top) / pinRange));
                chapter.el.style.setProperty('--cosmic-section-t', t.toFixed(4));
            }
            if (probe >= chapter.top) {
                activeIndex = index;
            }
        });

        if (activeIndex !== this._activeChapter && activeIndex >= 0) {
            this._activeChapter = activeIndex;
            const chapter = this._chapters[activeIndex];
            if (chapter === undefined) {
                throw new Error('cosmic-scroll: chapter index out of range');
            }
            this._scene.hue = chapter.hue / 360;
            this._scene.chapter = activeIndex;
            this._scene.setChapterLabel(chapter.label);
            this._rail.chapterIndex = activeIndex;
            this._rail.chapterLabel = chapter.label;
        }

        this._raf = requestAnimationFrame(this._frame);
    };
}
