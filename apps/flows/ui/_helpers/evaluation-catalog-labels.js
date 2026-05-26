const EVALUATION_CATALOG_IDS = new Set([
    'contains',
    'not_contains',
    'regex',
    'json_schema',
    'rouge_l',
    'bleu',
    'toxicity',
    'safety',
    'groundedness',
    'answer_relevance',
    'tool_accuracy',
    'pairwise_llm',
    'pairwise_human',
]);

const EVALUATION_CATALOG_CATEGORIES = new Set([
    'deterministic',
    'safety',
    'retrieval',
    'llm_judge',
    'trace',
    'pairwise',
]);

function requireKnownValue(value, allowed, label) {
    if (allowed.has(value)) {
        return value;
    }
    throw new Error(`${label}: unsupported value "${value}"`);
}

export function evaluationCatalogNameKey(evaluatorId) {
    const value = requireKnownValue(evaluatorId, EVALUATION_CATALOG_IDS, 'evaluation catalog evaluator_id');
    return `evaluation.evaluator_catalog.${value}.name`;
}

export function evaluationCatalogDescriptionKey(evaluatorId) {
    const value = requireKnownValue(evaluatorId, EVALUATION_CATALOG_IDS, 'evaluation catalog evaluator_id');
    return `evaluation.evaluator_catalog.${value}.description`;
}

export function evaluationCatalogCategoryKey(category) {
    const value = requireKnownValue(category, EVALUATION_CATALOG_CATEGORIES, 'evaluation catalog category');
    return `evaluation.evaluator_catalog.categories.${value}`;
}
