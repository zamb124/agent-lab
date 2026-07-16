# Runet indexing research — протокол и факты (Phase 0b)

Сжатая выжимка из плана runet pointer search: обсуждения §0.7–§0.8 и фактическая база §12–§18. Полный текст — в плане реализации.

## §0.7 — баланс мнений и фактов

### Три слоя сжатия (не путать)

1. **Extractor (trafilatura):** теряем boilerplate/JS; необратимо без raw HTML.
2. **Bi-encoder embed:** тысячи токенов → 1024 float mean-pool; всегда теряет детали.
3. **Storage quant (MRL/halfvec/int8/PQ):** теряет точность similarity; частично лечится two-stage rescore.

Для pointer-index один embed на страницу **достаточен для URL routing**; полнота — live fetch.

### Chunking — разнящиеся мнения

| Источник | Позиция |
|----------|---------|
| NAACL 2025 | Semantic часто не окупает cost; fixed-size не хуже на реальных данных |
| Adaptive Chunking 2026 | Per-document strategy +10pp correctness |
| Weaviate / NeuroLink | Markdown → heading-based; unknown → recursive |

**Правило проекта:** только **наш golden set RU**. BEIR biased к self-contained chunks.

Текущий `semantic` в conf — гипотеза; на crawl не применяется (фактически pgvector 1000/100).

### Лексика vs dense

- BEIR: ни один метод не побеждает везде; BM25 strong zero-shot.
- Hybrid + RRF k≈60 — industry default; у нас hybrid уже есть.
- Gap: `to_tsvector('simple')` без RU-стемминга — измеримый риск для runet.

### Vector compression

Порядок внедрения: **page-card** → MRL 512 halfvec → PQ только при нехватке GB. Quantization не чинит плохой split.

### LLM: три роли

| Роль | As-is | Target |
|------|-------|--------|
| Display title | LLM page_summary | `html_title` → H1 |
| Index text | LLM replace markdown | page-card + salient_terms |
| Chunk enrichment | NoOp / crawl LLM отдельно | gated Contextual Retrieval |

### Согласование pointer-модели с chunk-RAG

| Проблема | As-is chunk-RAG | Pointer-index |
|----------|-----------------|---------------|
| Storage | full markdown × chunks | multi-vector teasers K≤12 |
| Staleness | ttl=0 | hash + live fetch |
| Title | H1/LLM/Untitled | html_title + salient_terms |
| Passage retrieval | chunk search | live fetch + conditional embed |

## §0.8 — чеклист принятых решений

- Не зеркалить полный веб в `vector_documents`.
- Live fetch = pipeline в памяти запроса.
- `html_title`/meta из trafilatura (Phase 0).
- Дедуп URL в search (top-10 статей).
- Eval harness 200+ RU + rare-term subset.
- Shadow A/B chunking arms на eval slice.
- Pluggable `index_study_strategy`: lexical | split_embed | llm_embed | hybrid_study.
- Multi-vector per URL; collapse при search.
- Без миграций БД: `content="."` заглушка.

## §12 — три слоя сжатия (справка)

| Слой | Что теряется | Обратимо? |
|------|--------------|-----------|
| Trafilatura | nav/footer/JS | Только с raw HTML |
| Bi-encoder | детали внутри chunk | Нет |
| Quantization | точность distance | Частично (rescore) |

Ориентир: 1M chunks × 1024d ≈ **6–8 GiB**. Pointer page-card: **−70–85%** vs full-chunk.

## §13 — Chunking eval matrix (shadow arms)

Реализация: `core/search/index_study/chunking_arms.py`.

| Arm ID | Split | Назначение |
|--------|-------|------------|
| `as_is` | pgvector 1000/100 | Baseline |
| `fixed_512` | fixed_tokens 512/50 | NAACL control |
| `structure_800` | structure 800/120 | Primary challenger |
| `recursive_512` | recursive 512 | Universal fallback |
| `semantic_800` | semantic 800/120 | conf runet_web гипотеза |
| `llm_page_meta_only` | structure + LLM metadata only | display vs index |

Shadow namespace: `runet:eval:chunk:{arm_id}` на фиксированном URL slice (5–10k URL).

Метрики: nDCG@10, Recall@20, MRR@10, `url_recall@10`, `%Untitled`, chunks/doc, GB index, p95, LLM $/1k pages.

## §17 — Eval harness

Реализация: `apps/search/eval/`.

- Golden set: `apps/search/eval/data/golden_queries.jsonl` — **только ручная разметка** query→реальный URL (без автогенерации slug). Проверка: `uv run python apps/search/eval/data/validate_golden_queries.py`.
- Цель 200+ запросов — backlog: разметка по crawl slice / RusBEIR, не синтетика.
- Arms: chunking + index_study через `list_eval_arm_configs()`.
- Метрики: `url_recall@10`, `nDCG@10`, `MRR@10`, `rare_term_url_recall@10`, `url_dedup_purity@K`.

### Протокол Phase 0b

1. Зафиксировать baseline `as_is` на eval slice.
2. Прогнать shadow arms без смены prod namespace `runet`.
3. Сравнить по §13.4 метрикам; решение только по golden L1 + rare-term subset.
4. Победитель chunking — input для Phase 1 in-page conditional embed, не для persistent mirror.

## §18 — Priority matrix (P0 Phase 0)

| Изменение | Priority | Фаза |
|-----------|----------|------|
| trafilatura metadata | P0 | 0 |
| Eval harness + golden | P0 | 0 |
| URL dedup в index search | P0 | 0 |
| Markdown→ParsedDocument blocks | P1 | 0b |
| Query-aware snippet | P1 | 2 |
| Full-chunk mirror | Reject | — |
