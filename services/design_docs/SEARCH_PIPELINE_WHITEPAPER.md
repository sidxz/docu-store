# Intelligent Document Search for Scientific Research: Architecture and Rationale

> A technical white paper describing the multi-stage search pipeline implemented in docu-store,
> a document management platform for scientific research teams.
>
> **Audience**: Research product owners, technical stakeholders, and team leads evaluating
> search infrastructure for scientific document platforms.

---

## Executive Summary

Scientific research documents present unique challenges for search systems. Unlike general web content, research documents contain dense domain-specific terminology, chemical identifiers, gene names, institutional codes, and quantitative measurements that are meaningless to generic search models. A researcher searching for "NadD inhibitors with IC50 below 10uM from TAMU" is combining a protein target, a measurement type, a numeric threshold, and an institutional abbreviation into a single query. No single search technique handles all of these well.

This white paper describes a multi-stage search pipeline designed specifically for this problem space. The architecture combines seven complementary techniques -- semantic vector search, exact-term retrieval, hybrid fusion, cross-encoder reranking, contextual embedding enrichment, multi-granularity search, and metadata-driven filtering -- into a unified system that balances recall, precision, and performance.

The result is a search system where:
- Semantic queries ("mechanisms of drug resistance") find conceptually relevant passages even when exact terms differ
- Identifier queries ("SACC-111", "NadD") achieve perfect recall through exact-term matching
- Multi-faceted queries combine both signals for comprehensive results
- Cross-encoder reranking elevates the most relevant results, even when initial retrieval ranks them poorly
- Document context follows every chunk, so "The IC50 was 2.3 uM" is understood in terms of which compound, target, and study it belongs to

---

## 1. The Problem: Why Scientific Search Is Hard

### 1.1 The Vocabulary Gap

Dense embedding models (the neural networks that power semantic search) are trained on broad internet text. They learn rich representations for common language -- they understand that "drug resistance" and "antimicrobial tolerance" are related concepts, even though they share no words. This is their strength.

Their weakness is domain-specific identifiers. A compound code like "SACC-111", a gene name like "NadD", or an institutional abbreviation like "TAMU" are effectively unknown tokens to these models. During training, the model never encountered these strings in sufficient context to learn meaningful representations. When a researcher searches for "SACC-111", the model produces a low-quality vector that captures something like "unknown alphanumeric code" rather than "this specific compound from this specific study."

This is not a flaw in the model -- it is a fundamental limitation of representing text as dense numerical vectors. The solution is not a better model, but a complementary retrieval mechanism that guarantees exact-term recall.

### 1.2 The Context Problem

Research documents are typically processed by splitting them into smaller segments (chunks) for indexing. This is necessary because embedding models have limited input capacity and because users want to find specific passages, not entire documents. But chunking creates an information loss problem.

Consider a chunk that reads: "The IC50 was 2.3 uM against the target, showing potent inhibition." In isolation, this embeds as a generic statement about an IC50 measurement. The embedding captures the concept "IC50 measurement with potent result" but carries no information about which compound was tested, which protein was targeted, or which research group conducted the study. If a researcher searches for "NadD inhibitors with potent IC50", this chunk might not surface because its embedding doesn't encode the NadD context.

The chunk knows what happened ("IC50 was 2.3 uM") but not where it happened (page 7 of a study on NadD inhibitors from TAMU). This contextual information exists in the parent document but is lost during chunking.

### 1.3 The Granularity Problem

Researchers search at different levels of specificity. Sometimes they want a high-level overview: "What do we know about NadD as a drug target?" Other times they want a specific data point: "What was the IC50 of SACC-111?" A system that only indexes text chunks serves the second query well but forces the first query to piece together an answer from scattered fragments. A system that only indexes document summaries serves the first query well but cannot locate specific passages.

The solution is multi-granularity search -- indexing the same content at multiple levels of abstraction and letting the search pipeline query across granularities simultaneously.

### 1.4 The Precision Problem

Vector similarity search is inherently approximate. It retrieves candidates that are "close" in embedding space, but closeness does not always equal relevance. A passage about IC50 measurements for a different compound might be very close in embedding space to the desired passage about a specific compound. The first-stage retrieval returns a candidate set that contains the right answers but may not rank them optimally.

This is where two-stage retrieval becomes essential. A lightweight first stage casts a wide net to identify candidate passages, then a more powerful (and more expensive) second stage re-scores each candidate by examining the query and passage text jointly. This reranking step can dramatically reorder results, promoting a buried but highly relevant result from position 15 to position 1.

---

## 2. Architecture Overview

The search pipeline is structured as a multi-stage system with three parallel search collections, a hybrid retrieval engine, and a cross-encoder reranking layer.

### 2.1 Three Search Collections

The system maintains three separate vector collections, each optimized for a different type of search:

**Text Chunk Collection** -- The primary collection. Every document page is split into overlapping text segments, and each segment is indexed with both a dense semantic vector and a sparse term-frequency vector. This collection supports full hybrid search with metadata filtering and is the target of most user queries.

**Summary Collection** -- A unified collection containing both page-level and artifact-level summaries. Each summary captures the high-level meaning of a page or an entire document. This collection enables "big picture" queries that would be difficult to answer from individual text chunks. Page summaries and artifact summaries coexist in the same collection, distinguished by a type field, allowing cross-granularity retrieval in a single query.

**Compound Collection** -- A specialized collection for chemical structural similarity. Each compound mentioned in the research documents is encoded using a chemistry-specific embedding model (ChemBERTa) that understands molecular structure represented as SMILES notation. This enables queries like "find compounds structurally similar to this molecule" -- a fundamentally different search modality from text search.

### 2.2 The Search Pipeline Stages

A typical search query flows through four stages:

**Stage 1: Query Encoding** -- The user's query text is transformed into two representations: a dense vector that captures semantic meaning, and a sparse vector that captures exact terms. For chemical queries, the SMILES string is encoded using the chemistry-specific model instead.

**Stage 2: Hybrid Retrieval** -- Both representations are sent to the vector database simultaneously. The dense vector retrieves semantically similar passages; the sparse vector retrieves passages containing the exact query terms. The results from both channels are fused using a rank-based algorithm that combines the best of both worlds. Metadata filters (workspace, tags, entity types) are applied at this stage, before any results are returned.

**Stage 3: Cross-Encoder Reranking** -- The top candidates from hybrid retrieval are re-scored by a cross-encoder model that reads the query and each candidate passage together. This joint reading is much more powerful than the independent encoding used in Stage 2 -- it can detect subtle relevance signals like negation, specificity, and argumentative structure that embedding similarity alone cannot capture.

**Stage 4: Enrichment** -- The final ranked results are enriched with metadata from the application database: document titles, page numbers, tags, compound mentions, and text previews. This metadata is presented to the user alongside the search results.

---

## 3. Key Concepts in Depth

### 3.1 Dense Embeddings: Capturing Meaning as Geometry

At the foundation of the search system are dense vector embeddings -- fixed-size numerical representations of text that capture semantic meaning. The system uses nomic-embed-text-v1.5, a 768-dimensional embedding model that maps any text passage to a point in a 768-dimensional space. Passages with similar meanings end up near each other in this space.

This geometric property is what makes semantic search possible. When a researcher queries "mechanisms of antibiotic resistance," the query is mapped to a point in embedding space. The search engine then finds text chunks whose embeddings are closest to the query's embedding, as measured by cosine similarity (the angle between two vectors). Passages about "antimicrobial tolerance pathways" or "drug efflux pump mechanisms" will have embeddings close to the query, even though they use different words.

**Why nomic-embed-text-v1.5?** This model was selected over the initial lightweight model (all-MiniLM-L6-v2, 384 dimensions) for three reasons. First, it produces higher-quality embeddings on retrieval benchmarks, particularly for domain-specific text. Second, it supports asymmetric retrieval through task prefixes -- queries and documents are encoded differently, which improves retrieval accuracy because a question and a passage that answers it are linguistically different even when semantically related. Third, it doubles the embedding dimensionality (768 vs 384), providing a richer representation space for capturing subtle meaning differences.

### 3.2 Sparse Embeddings: Guaranteeing Exact-Term Recall

Dense embeddings excel at semantic similarity but fail on opaque identifiers. To solve this, the system generates a second representation for each text chunk: a sparse hashing-based vector. Unlike dense vectors, which are compact and capture meaning holistically, sparse vectors are high-dimensional and capture individual terms.

The system uses scikit-learn's **HashingVectorizer** to produce sparse vectors. For each term in a passage, the vectorizer computes a term-frequency weight and maps the term to a fixed index using a deterministic hash function. The resulting sparse vector has 2^18 (~262,000) dimensions. Most dimensions are zero -- only the terms present in the passage have non-zero weights. L2 normalization is applied so that longer passages do not dominate shorter ones.

This approach guarantees that a query containing "SACC-111" will match passages containing that exact string, regardless of whether the dense embedding model understands the term.

**Why hashing over TF-IDF with vocabulary fitting?** The system initially used scikit-learn's TfidfVectorizer, which produces higher-quality weights through IDF (Inverse Document Frequency) -- downweighting common terms and boosting rare ones. However, TfidfVectorizer requires fitting a vocabulary on the corpus, which creates an operational problem: the vocabulary becomes stale as new documents are ingested. Re-fitting changes vocabulary indices, invalidating all existing sparse vectors in the vector database and requiring a full re-embedding. For a long-running service processing documents continuously, this maintenance burden was unacceptable.

HashingVectorizer eliminates this entirely. Terms are mapped to indices via a deterministic hash function -- the same term always maps to the same index, regardless of when the document was ingested. No fitting, no persistence, no stale vocabulary, no re-embedding. The tradeoff is the loss of IDF weighting (common terms like "enzyme" are not downweighted), but this is mitigated by two factors:

1. **RRF fusion is rank-based, not score-based.** Even without IDF, the passage containing "SACC-111" still ranks first in sparse results for a "SACC-111" query. The RRF score is determined by rank position, not by the absolute sparse score.

2. **Cross-encoder reranking compensates.** The reranker reads query and passage text jointly, so it naturally distinguishes between a passage that centrally discusses a query term and one that merely mentions it in passing. The ranking quality that IDF would have provided at the sparse retrieval stage is recovered at the reranking stage.

**Custom tokenization**: The tokenizer is configured with a custom pattern (`\b\w[\w\-\.]+\b`) that preserves hyphens and dots in tokens. This ensures scientific identifiers like "SACC-111", "IC50", "NZ-967", and "NadD/E" are treated as single tokens rather than being split at punctuation boundaries. Bigram capture (ngram_range 1-2) is enabled so that multi-word terms like "drug resistance" are indexed as a single unit alongside their individual words.

### 3.3 Reciprocal Rank Fusion: Combining Two Worlds

Dense and sparse retrieval each return a ranked list of candidates. These lists often overlap but differ in ordering -- a passage might rank 3rd by semantic similarity but 1st by term matching. The challenge is combining these two signals into a single, unified ranking.

The system uses Reciprocal Rank Fusion (RRF), a technique that works purely on rank positions rather than raw scores. This is important because dense and sparse scores are on fundamentally different scales and cannot be directly compared or averaged.

RRF assigns each result a score based on its rank position: score = 1/(k + rank), where k is a constant (typically 60). A result ranked 1st gets a score of 1/61; a result ranked 10th gets 1/70. If a result appears in both the dense and sparse lists, its RRF scores from both lists are summed. Results that rank highly in both retrieval channels receive the highest combined scores, while results that rank highly in only one channel still contribute.

**Why RRF matters for scientific search**: Consider the query "SACC-111 inhibitor potency". The dense retrieval channel surfaces passages about inhibitor potency in general (semantic match), while the sparse channel surfaces passages mentioning SACC-111 specifically (term match). A passage that discusses SACC-111's potency data appears in both lists and rises to the top of the fused ranking. A passage about a different inhibitor's potency appears only in the dense list and ranks lower. This behavior is exactly what a researcher would expect.

The fusion is performed entirely within the vector database using its native prefetch-and-fuse capability. Both retrieval channels run in parallel, each fetching up to 100 candidates, and fusion occurs server-side before results are returned. This eliminates application-level merge logic and minimizes network overhead.

### 3.4 Cross-Encoder Reranking: Joint Relevance Scoring

The initial retrieval stages (dense, sparse, or hybrid) use bi-encoder models: the query and each document are encoded independently, and relevance is estimated by comparing their embeddings. This is fast -- you encode the query once and compare it against pre-computed document embeddings -- but it is also limited. The model never "reads" the query and document together, so it cannot detect subtle interaction effects.

Cross-encoder reranking is a second-stage process that scores each (query, passage) pair jointly. The cross-encoder model receives the query and a candidate passage as a single concatenated input and produces a relevance score. Because it attends to both texts simultaneously, it can detect:

- **Specificity**: Whether the passage actually answers the query or just discusses the same topic
- **Negation**: Whether the passage contradicts the query (e.g., "NadD was NOT the target")
- **Argument structure**: Whether the query concept is the main subject or a peripheral mention
- **Quantitative relevance**: Whether numeric values in the passage match the query's intent

The tradeoff is speed: cross-encoder scoring requires a forward pass for every (query, candidate) pair, making it impractical for full-collection search. This is why it is used as a second stage: hybrid retrieval narrows the candidate set to approximately 30 passages (3x the desired result count), and the cross-encoder rescores only these candidates.

**Model selection**: The cross-encoder model (ms-marco-MiniLM-L-12-v2) was chosen to balance quality and latency. It was trained on one of the largest passage ranking datasets, providing high-quality relevance scores, while remaining small enough to rescore 30 passages in under 200 milliseconds on CPU. The system also tracks reranking diagnostics -- how far each result moved in rank after reranking -- which provides valuable quality signal for monitoring and tuning.

**Measurable impact**: In information retrieval benchmarks, cross-encoder reranking typically improves precision@10 (the fraction of top-10 results that are relevant) by 10-30%. For scientific queries with subtle relevance criteria, the improvement can be even larger because the cross-encoder captures domain-specific signals that embedding similarity alone misses.

### 3.5 Contextual Chunk Embeddings: Giving Chunks Their Memory

As discussed in Section 1.2, text chunks lose their parent document's context during segmentation. The system addresses this with contextual chunk embeddings -- a technique where each chunk is prepended with a context header before being passed to the embedding model.

The context header contains four elements drawn from the parent document:

1. **Document title** -- Anchors the chunk to its source document. A chunk from "NadD Inhibitor Screening Results" embeds differently than the same text from "Kinase Panel Selectivity Data."

2. **Tags** -- Named entities extracted from the page by the NER pipeline (protein targets, compound names, gene names, diseases). These inject domain-specific terms into the embedding input, ensuring the resulting vector captures the chunk's biological context.

3. **Page position** -- The page number within the document. This is a weak signal but helps distinguish introductory material from results sections.

4. **Page summary** -- A condensed summary of the page's content (capped at 200 characters). This provides semantic context that complements the specific detail in the chunk.

The key insight is that this context header affects only the embedding computation, not the stored text. The raw chunk text is preserved in the database for display to users. The context header is used solely to produce a richer, more contextually aware vector representation.

**The timing challenge**: Context enrichment depends on data that isn't available when chunks are first indexed. When a document is uploaded, the text is extracted and chunked immediately, but tags (from NER) and summaries (from LLM summarization) are produced by later pipeline stages. The system handles this with a two-pass approach:

1. **Initial embedding**: Chunks are embedded without context (or with partial context) immediately after text extraction. This ensures results are searchable within seconds of upload.

2. **Context-enriched re-embedding**: When the page summary becomes available (the last piece of context), the pipeline automatically triggers a re-embedding of all chunks with the full context header. This overwrites the initial embeddings with higher-quality contextual ones.

This two-pass architecture is event-driven -- the system's event pipeline automatically triggers re-embedding when the right events fire, with no manual intervention or scheduling required.

### 3.6 Multi-Granularity Search: Chunks, Summaries, and Documents

The system indexes content at three levels of granularity:

**Chunk level** -- Individual text segments (approximately 1000 characters, with 200-character overlap between consecutive chunks). This is the finest granularity and supports precise passage retrieval. Overlap ensures that no information is lost at chunk boundaries.

**Page summary level** -- Each document page is summarized by a language model, and the summary is indexed as a single vector. Page summaries capture the overall theme and key findings of a page, enabling broader queries that would require piecing together multiple chunks.

**Artifact summary level** -- Entire multi-page documents are summarized using a sliding-window approach (batch pages, synthesize, refine) and the result is indexed. Artifact summaries support the broadest queries: "What is this paper about?" or "Which documents discuss NadD?"

All three granularities live in two collections (chunks in one, page + artifact summaries in another), and the hierarchical search endpoint queries both collections in parallel. Results are returned separately by granularity, giving the client application flexibility in how to present them -- for example, showing document-level matches as expandable cards with page-level and chunk-level results nested beneath.

**Why separate collections?** Page and artifact summaries share the same embedding model and vector dimensionality, so they coexist naturally in a single unified collection with a type discriminator. Text chunks, however, have a fundamentally different schema (chunk indices, sparse vectors, per-chunk metadata) and benefit from independent configuration (quantization, sparse vector support). Keeping them separate also allows independent scaling and tuning.

### 3.7 Metadata-Driven Filtering: Combining Structured and Unstructured Search

Vector similarity alone is necessary but not sufficient for scientific search. Researchers frequently know structured facts about what they're looking for: "I want results about NadD" (a specific target), "only from this document" (a specific artifact), "only showing compounds" (an entity type). Pure semantic search cannot enforce these constraints -- it can only approximate them through embedding similarity.

The system stores structured metadata alongside every vector and supports filter-based search that combines structured constraints with semantic retrieval. Key filterable fields include:

- **Workspace ID** -- Multi-tenant isolation. Every query is automatically scoped to the user's workspace, ensuring that one team's documents never appear in another team's search results.

- **Tags** -- Named entities extracted by the NER pipeline (compound names, protein targets, gene names, diseases, institutions). These are stored in a normalized (lowercased) form for case-insensitive matching. Researchers can filter by tag ("show me everything mentioning NadD") or by entity type ("show me all results tagged with a protein target").

- **Tag match mode** -- Filters can operate in "any" mode (results must contain at least one of the specified tags) or "all" mode (results must contain every specified tag). This supports both exploratory browsing and precise filtering.

- **Artifact scoping** -- Results can be restricted to a specific document or a set of allowed documents. This is essential for document-specific search ("search within this paper").

Tags are synchronized to vector payloads without re-embedding -- when NER results become available (which may happen after initial embedding), the system patches the tag metadata onto existing vector points using a payload update operation. This takes less than 10 milliseconds per page and avoids the computational cost of regenerating embeddings.

### 3.8 Server-Side Deduplication: One Result Per Page

When searching the text chunk collection, multiple chunks from the same page often match a query. Returning all of them is redundant and clutters the result list. The system uses server-side deduplication to return only the best-scoring chunk per page.

This is implemented using the vector database's native grouping capability, which groups result candidates by a payload field (page ID) and returns only the top-scoring member of each group. The operation is performed entirely within the vector database, eliminating the need for application-level post-processing.

Before this optimization was implemented, the system used a "3x over-fetch" strategy: retrieve three times the desired result count, then deduplicate in application code. This approach had three problems: it transferred 3x more data over the network, it computed similarity scores for candidates that would ultimately be discarded, and it added code complexity. Server-side grouping solves all three problems simultaneously.

### 3.9 Chemical Structural Similarity Search

Research documents in drug discovery contain references to chemical compounds, typically represented as SMILES (Simplified Molecular-Input Line-Entry System) strings -- a text notation that encodes molecular structure. The system extracts these SMILES strings during document processing and indexes them using ChemBERTa, a transformer model pre-trained on molecular data.

ChemBERTa maps SMILES strings to 384-dimensional vectors that capture structural properties of molecules. Structurally similar compounds (e.g., analogues in a medicinal chemistry series) produce vectors that are close together in embedding space. This enables a fundamentally different search modality: given a compound of interest, find all documents that mention structurally similar compounds.

This collection uses dense-only search (no sparse vectors) because term matching is not meaningful for SMILES strings -- the relationship between molecular structure and SMILES character sequences is non-trivial and not captured by string-level tokenization.

### 3.10 Scalar Quantization: Performance at Scale

As collections grow, storing full-precision (32-bit floating point) vectors for every chunk becomes memory-intensive. The system applies scalar quantization to the text chunk collection -- the largest collection -- reducing each vector component from 32-bit to 8-bit integer representation.

This compression reduces memory consumption by approximately 4x with less than 1% quality loss on retrieval benchmarks. To mitigate the small quality loss, the system uses oversampling with rescoring: initial candidate retrieval is performed on quantized vectors (2x more candidates than needed), and the final ranking is computed using the original full-precision vectors. This two-pass approach within the vector database achieves nearly identical quality to unquantized search at a fraction of the memory cost.

Quantization is currently applied only to the text chunk collection, which has the most points (one per chunk per page). The summary and compound collections are smaller and do not yet require this optimization.

---

## 4. The Event-Driven Indexing Pipeline

Search quality depends on keeping the vector index synchronized with the document processing pipeline. The system uses an event-driven architecture where domain events trigger indexing operations automatically, ensuring that search results reflect the latest state of document processing.

### 4.1 The Indexing Sequence

When a new document is uploaded, the following event chain drives search indexing:

1. **Text extraction** produces raw page text, emitting a text-updated event.

2. **Initial chunk embedding** -- The text is chunked, and each chunk is embedded (dense + sparse) and indexed. At this stage, contextual enrichment is minimal because tags and summaries don't exist yet.

3. **NER extraction** runs in parallel, extracting named entities (targets, compounds, genes) from the page text. When complete, a tag-updated event fires. The pipeline responds by patching the tag metadata onto the existing chunk vectors (no re-embedding required) and syncing tags to the summary collection.

4. **Summarization** runs after embedding completes (sequential, not parallel, to avoid resource contention). When the page summary is produced, a summary-updated event fires. This triggers three actions:
   - The page summary is embedded and indexed in the summary collection
   - All text chunks are re-embedded with the full context header (document title + tags + summary)
   - The system checks whether all pages in the document have been summarized; if so, it triggers document-level summarization

5. **Document-level summarization** aggregates page summaries into a single document summary, which is then embedded and indexed in the summary collection.

This sequence is orchestrated by a durable workflow engine that guarantees exactly-once execution, automatic retries on failure, and visibility into pipeline state. Each indexing operation is a workflow activity with configurable timeouts and retry policies.

### 4.2 Idempotent Operations

All indexing operations are idempotent -- running the same operation twice produces the same result. Point IDs are deterministic (computed from page ID and chunk index), so re-indexing a page overwrites the previous vectors rather than creating duplicates. Deletion operations check for existence before acting. This idempotency is essential for reliability in an event-driven system where events may be delivered more than once.

---

## 5. Search Endpoints and Use Cases

The system exposes four search endpoints, each serving a distinct research workflow:

### 5.1 Text Search

The primary search endpoint queries the text chunk collection using the full hybrid pipeline (dense + sparse retrieval, RRF fusion, cross-encoder reranking, metadata filtering). This is the "power search" that handles everything from simple keyword lookups to complex multi-concept queries.

Researchers use this endpoint when they know what they're looking for and want specific passages: "What was the IC50 of compound X against target Y?" or "Find mentions of drug resistance mechanisms in this document."

Results include the original text passage, the parent document's title and metadata, similarity and reranking scores, and a text preview for quick scanning.

### 5.2 Summary Search

Queries the summary collection for high-level results. Researchers use this endpoint for exploratory queries: "What do we know about NadD as a drug target?" or "Which documents discuss tuberculosis treatment?"

Results can be filtered by granularity (page summaries only, document summaries only, or both) and by tags. Each result includes the full summary text, eliminating the need for additional database lookups.

### 5.3 Hierarchical Search

Queries both collections in parallel and returns results grouped by granularity. This endpoint is designed for search UIs that want to present a multi-level view: document-level matches as cards, with page-level summaries and specific passage hits nested beneath.

The client receives summary hits and chunk hits as separate lists, giving the frontend complete control over how to merge and present them. This separation of concerns keeps the search backend focused on retrieval quality while allowing the frontend to experiment with presentation.

### 5.4 Compound Search

Queries the compound collection using a SMILES input string. The input is validated and canonicalized before embedding. Results return structurally similar compounds with their source pages and confidence scores.

This endpoint serves a specialized but important use case in drug discovery: "Given this lead compound, where else in our research corpus do we see similar structures?"

---

## 6. Design Decisions and Tradeoffs

### 6.1 Local Models vs API-Based Services

All embedding, sparse encoding, and reranking models run locally (on CPU by default, with GPU support available). This decision was driven by three factors:

- **Data sovereignty**: Research documents may contain pre-publication data, proprietary compounds, or confidential results. Sending this text to external API services introduces compliance risk.
- **Latency predictability**: Local inference provides consistent, low-variance latency without network dependency. Search queries complete in under 500ms regardless of external service availability.
- **Cost at scale**: API-based embedding services charge per token. For a research platform that re-indexes documents multiple times (initial embedding, contextual re-embedding, model upgrades), local inference eliminates a significant variable cost.

### 6.2 Three Collections vs One Unified Collection

Keeping text chunks, summaries, and compounds in separate vector collections (rather than one collection with type filters) provides several benefits:

- **Independent optimization**: The text chunk collection uses sparse vectors, quantization, and oversampling; the summary collection uses dense-only search; the compound collection uses a different embedding model and dimensionality. These configurations would conflict in a shared collection.
- **Independent scaling**: Text chunks are the largest collection by far (many chunks per page per document). Scaling it independently avoids over-provisioning for the smaller collections.
- **Schema clarity**: Each collection has a clean, focused schema without conditional fields.

### 6.3 Hashing-Based Sparse Vectors vs Alternatives

The system uses HashingVectorizer for sparse vectors rather than TfidfVectorizer or learned sparse models like SPLADE. This decision was driven by operational robustness:

- **No vocabulary fitting**: TfidfVectorizer requires fitting IDF weights on the corpus, which creates stale vocabulary problems in long-running containers. Re-fitting invalidates all existing sparse vectors. HashingVectorizer eliminates this class of problems entirely.
- **Deterministic indexing**: The same term always hashes to the same vector index, regardless of corpus state. Documents ingested months apart produce compatible sparse vectors with no coordination.
- **Custom tokenization**: The tokenizer preserves scientific notation (hyphens in compound codes, dots in version numbers) and captures bigrams. This level of control is harder to achieve with pre-trained sparse models like SPLADE, which use BERT's WordPiece tokenizer and would split "SACC-111" into subword pieces.
- **Zero maintenance**: No model files to persist, no scheduled re-fitting jobs, no pkl corruption risk, no concurrency issues with multiple workers.

The tradeoff is the loss of IDF weighting -- common terms are not downweighted at the sparse retrieval stage. This was evaluated against the alternatives:

- **TfidfVectorizer**: Better ranking quality via IDF, but vocabulary staleness in production makes it impractical without periodic re-fitting and re-embedding of all vectors.
- **SPLADE**: Higher-quality sparse representations with term expansion, but uses BERT's WordPiece tokenizer which splits scientific identifiers into subwords, degrading exact-term recall for the system's primary sparse search use case.
- **BM25**: Requires corpus statistics similar to TF-IDF, with the same fitting/staleness problems.

The cross-encoder reranker effectively compensates for the IDF quality gap, making hashing-based sparse vectors the pragmatic choice for this system.

### 6.4 Event-Driven Re-Embedding vs Scheduled Batch Jobs

The contextual re-embedding strategy (re-embed chunks when summaries become available) uses event-driven triggers rather than scheduled batch jobs. This ensures:

- **Freshness**: Re-embedding happens immediately when the context becomes available, not at the next scheduled batch window.
- **Efficiency**: Only affected chunks are re-embedded, not the entire collection.
- **Reliability**: The durable workflow engine guarantees that re-embedding completes even if the system crashes mid-operation.
- **Observability**: Each re-embedding operation is a tracked workflow with retry history and timing data.

---

## 7. What This Means for Research Teams

For researchers, the search system provides a unified interface that handles the full spectrum of scientific queries without requiring expertise in search technology. A researcher can:

- Search by concept ("drug resistance mechanisms") and get semantically relevant results
- Search by identifier ("SACC-111") and get exact matches, guaranteed
- Combine both in a single query and get results ranked by both signals
- Filter by known entities ("show me results about NadD from TAMU")
- Browse at document level or drill into specific passages
- Find structurally similar compounds across the entire corpus

For product owners, the architecture provides:

- **Measurable quality signals**: Reranking diagnostics, similarity scores, and promotion tracking provide quantitative evidence of search quality that can be monitored over time.
- **Modular upgradeability**: Each pipeline stage (embedding model, sparse method, reranker, vector database) can be independently upgraded without rewriting the system. Moving from TF-IDF to a learned sparse model, or upgrading the embedding model, requires changing a single adapter.
- **Cost-effective scaling**: Quantization and server-side grouping reduce infrastructure costs as the collection grows. Local model inference eliminates per-query API costs.
- **Multi-tenant isolation**: Workspace-scoped filtering ensures that search results never leak across team boundaries, which is essential for organizations managing multiple research programs.

---

## 8. Future Directions

The architecture anticipates several extensions that can be added without restructuring the existing pipeline:

**Query Understanding** -- Decomposing complex queries into sub-queries ("NadD inhibitors with IC50 below 10uM from TAMU" becomes a semantic search for "NadD inhibitors" combined with a metadata filter for "TAMU" and a numeric constraint on IC50). This would be implemented as a pre-processing stage before the existing pipeline.

**Discovery and Recommendation** -- "Find more like these, but not like those" interactions, where researchers iteratively refine search results by providing positive and negative examples. The vector database already supports these operations natively.

**Hybrid Summary Search** -- Extending sparse vectors to the summary collection, enabling exact-term recall at the summary level. This follows the same pattern already implemented for text chunks.

**Learned Sparse Models** -- If IDF-quality term weighting becomes a measurable gap, SPLADE or similar learned sparse representations could be evaluated. The existing sparse embedding port abstracts this cleanly. However, any learned model must be evaluated against the custom tokenization requirements for scientific identifiers -- BERT-based tokenizers split compound codes into subwords, which may degrade exact-term recall.

---

## Appendix A: Technology Stack

| Component | Technology | Role |
|-----------|-----------|------|
| Vector database | Qdrant v1.16+ | Vector storage, hybrid search, RRF fusion, server-side grouping |
| Dense embedding model | nomic-ai/nomic-embed-text-v1.5 | 768-dimensional semantic embeddings |
| Sparse embedding | scikit-learn HashingVectorizer | Hashing-based sparse vectors for exact-term recall (no fitting required) |
| Cross-encoder reranker | cross-encoder/ms-marco-MiniLM-L-12-v2 | Two-stage relevance rescoring |
| Chemistry embedding | DeepChem/ChemBERTa-77M-MTR | 384-dimensional SMILES structural embeddings |
| Workflow orchestration | Temporal | Durable execution for indexing pipeline |
| Event store | EventStoreDB | Event sourcing for domain aggregates |
| Read model database | MongoDB | Materialized views for enrichment |
| Application framework | FastAPI | HTTP API layer |

## Appendix B: Glossary

| Term | Definition |
|------|-----------|
| **Bi-encoder** | A model that encodes query and document independently into vectors, then compares them by similarity. Fast but loses interaction signals. |
| **Cross-encoder** | A model that reads query and document together as a single input, producing a relevance score. Accurate but slow (one forward pass per pair). |
| **Cosine similarity** | A measure of angular similarity between two vectors. Values range from -1 (opposite) to 1 (identical direction). Used to rank search results. |
| **Dense vector** | A compact, fixed-size numerical representation (e.g., 768 numbers) that captures holistic semantic meaning. Every dimension carries a value. |
| **Sparse vector** | A high-dimensional representation where most values are zero. Each non-zero dimension corresponds to a specific term in the vocabulary. |
| **RRF (Reciprocal Rank Fusion)** | A rank-based fusion technique that combines ranked lists by summing reciprocal rank scores. Score-scale agnostic. |
| **TF-IDF** | Term Frequency-Inverse Document Frequency. A weighting scheme that scores terms based on local frequency (how often in this passage) and global rarity (how rare across all passages). Requires corpus fitting for IDF weights. |
| **HashingVectorizer** | A stateless sparse encoder that maps terms to vector indices via deterministic hashing. No vocabulary fitting required -- the same term always maps to the same index. Trades IDF weighting for operational simplicity. |
| **SMILES** | Simplified Molecular-Input Line-Entry System. A text notation for describing chemical structures (e.g., "C1=CC=CC=C1" represents benzene). |
| **Quantization** | Reducing numerical precision of stored vectors (e.g., 32-bit float to 8-bit integer) to save memory with minimal quality loss. |
| **Oversampling** | Retrieving more candidates than needed using quantized vectors, then rescoring with full-precision vectors for accuracy. |
| **Named vector** | A vector stored under a specific name within a multi-vector point. Enables storing dense and sparse vectors on the same data point. |
| **Prefetch** | A vector database operation that retrieves initial candidates from one vector channel before fusion or further processing. |
| **Idempotent** | An operation that produces the same result regardless of how many times it is executed. Essential for reliability in event-driven systems. |
