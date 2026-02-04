# DAIKON DOCU STORE

A human-first document intelligence store for drug discovery, built to keep scientific work explainable, searchable, and ready for the next breakthrough.

## Status

[![Tests](https://github.com/sidxz/docu-store/actions/workflows/tests.yml/badge.svg)](https://github.com/sidxz/docu-store/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![Event Sourcing](https://img.shields.io/badge/Event%20Sourcing-Yes-brightgreen)](https://martinfowler.com/eaaDev/EventSourcing.html)
[![CQRS](https://img.shields.io/badge/CQRS-Yes-brightgreen)](https://martinfowler.com/bliki/CQRS.html)
[![Kafka](https://img.shields.io/badge/Kafka-Streaming-000000?logo=apache-kafka&logoColor=white)](https://kafka.apache.org/)
[![MongoDB](https://img.shields.io/badge/MongoDB-ReadModels-13aa52?logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ed?logo=docker&logoColor=white)](https://www.docker.com/)

## Why it exists

Drug discovery generates a river of documents: experimental protocols, assay results, regulatory artifacts, and research narratives. Docu Store exists to keep that river navigable. We want a system where every update is traceable, every decision is defensible, and every insight is easy to rediscover.

## Capabilities

- **Event-sourced core** for durable provenance and rollback analysis.
- **CQRS read models** tuned for search, dashboards, and review flows.
- **Streaming integration** via Kafka to connect lab systems and pipelines.
- **API-first architecture** built on FastAPI.
- **AI-powered enrichment (in progress)**: OCR extraction of SMILES from images and PDFs, document embeddings across formats, and a vector database for semantic retrieval.

## Architecture at a glance

```mermaid
flowchart LR
    UI[Client / Integrations] --> API[FastAPI Command API]
    API -->|Commands| ES[(Event Store)]
    ES -->|Events| Kafka[Kafka Topics]
    Kafka --> Proj[Projection Workers]
    Proj --> RM[(MongoDB Read Models)]
    RM --> QAPI[FastAPI Query API]
    QAPI --> UI
```

## Event lifecycle

```mermaid
sequenceDiagram
    participant U as Scientist
    participant C as Command API
    participant E as Event Store
    participant K as Kafka
    participant P as Projector
    participant M as Read Models

    U->>C: Submit Document Update
    C->>E: Append Events
    E-->>K: Publish Events
    K-->>P: Stream Events
    P->>M: Update Projections
    M-->>U: Consistent Query Results
```

## Intelligence roadmap

Docu Store is in active development. The vision is to pair trustworthy data lineage with modern retrieval so scientists can move from “where is that file?” to “what does it imply?” in seconds.

```mermaid
flowchart TD
    Raw[Images / PDFs / Lab Docs] --> OCR[OCR + SMILES Extraction]
    Raw --> Parser[Structured Parsers]
    OCR --> Embed[Embedding Pipeline]
    Parser --> Embed
    Embed --> VectorDB[(Vector Database)]
    VectorDB --> Search[Semantic Search + Reranking]
    Search --> UI[Discovery UI / API]
```

## What makes it intelligent

- **Context-aware history**: every document state is derived, not overwritten.
- **Separation of concerns**: write paths stay correct, read paths stay fast.
- **Composable signals**: events and embeddings become reusable blocks for analytics.
- **Search that feels human**: semantic retrieval that understands chemistry artifacts and experimental context.
- **Operational clarity**: streaming pipelines are explicit, observable, testable.

## Next steps

- Skim `TESTING_QUICK_REFERENCE.md` for a fast local setup.
- Review `WORKER_SETUP.md` for projector and worker configuration.

## Features

- Event sourcing architecture
- CQRS pattern for read/write separation
- Kafka for event streaming
- MongoDB for read models
- FastAPI for REST API
