import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { normalizeLlmModelScoreList } from '../../../../apps/frontend/ui/events/resources/llm-model-scores.resource.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

beforeEach(() => {
    resetFactories();
});

afterEach(() => {
    resetFactories();
});

function validItem() {
    return {
        provider: 'openrouter',
        model_id: 'meta/llama',
        capability: 'llm_chat',
        score: 12.5,
        enabled: true,
        editorial_prior: 0,
        note: null,
        has_overlay_row: false,
        intelligence_index: null,
        coding_index: null,
        agentic_index: null,
        score_breakdown: { heuristic: 12.5 },
        updated_by_user_id: null,
        created_at: null,
        updated_at: null,
        availability: 'available',
        cooldown_seconds: null,
        error_class: null,
        error_text: null,
        http_status: null,
    };
}

function validProvider() {
    return {
        provider: 'openrouter',
        configured: true,
        availability: 'available',
        model_count: 1,
        blocked_model_count: 0,
        cooldown_seconds: null,
        error_class: null,
        error_text: null,
        http_status: null,
        last_probe: null,
    };
}

describe('normalizeLlmModelScoreList', () => {
    it('принимает полный list-контракт', () => {
        const normalized = normalizeLlmModelScoreList({
            items: [validItem()],
            providers: [validProvider()],
        });
        expect(normalized.items).toHaveLength(1);
        expect(normalized.providers).toHaveLength(1);
        expect(normalized.items[0]?.availability).toBe('available');
        expect(normalized.providers[0]?.provider).toBe('openrouter');
    });

    it('бросает без providers', () => {
        expect(() => normalizeLlmModelScoreList({
            items: [validItem()],
        })).toThrow(/providers must be an array/);
    });

    it('бросает без items', () => {
        expect(() => normalizeLlmModelScoreList({
            providers: [validProvider()],
        })).toThrow(/items must be an array/);
    });

    it('бросает без availability на item', () => {
        const item: { availability?: string } & Omit<ReturnType<typeof validItem>, 'availability'> = validItem();
        delete item.availability;
        expect(() => normalizeLlmModelScoreList({
            items: [item],
            providers: [validProvider()],
        })).toThrow(/availability is required/);
    });
});
