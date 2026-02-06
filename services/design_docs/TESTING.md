"""Test Suite Documentation

## Overview

This directory contains a comprehensive test suite for the docu-store project. The tests are organized by layer following the hexagonal architecture pattern:

- **domain/**: Tests for domain aggregates, value objects, and domain services
- **application/**: Tests for use cases, mappers, and DTOs
- **infrastructure/**: Tests for repositories, event projectors, and serialization
- **integration/**: End-to-end integration tests and workflow tests

## Test Structure

### Domain Layer Tests

#### test_artifact.py
Tests for the Artifact aggregate root including:
- Creation and initialization
- Page management (add/remove pages)
- Title mention updates
- Summary candidate updates
- Tag management
- Deletion and cascading effects
- Hashing behavior

#### test_page.py
Tests for the Page aggregate including:
- Creation and initialization
- Compound mention updates
- Tag mention updates
- Text mention updates
- Summary candidate updates
- Deletion
- Hashing behavior

#### test_value_objects.py
Tests for value objects including:
- ArtifactType enum
- MimeType enum
- TitleMention
- SummaryCandidate
- CompoundMention
- ExtractionMetadata
- TagMention
- TextMention

#### test_services.py
Tests for domain services:
- ArtifactDeletionService: Cascading deletion of artifacts and pages

### Application Layer Tests

#### test_mappers.py
Tests for mapper classes:
- ArtifactMapper: Mapping Artifact aggregates to DTOs
- PageMapper: Mapping Page aggregates to DTOs

#### test_dtos.py
Tests for Data Transfer Objects:
- CreateArtifactRequest validation
- ArtifactResponse creation
- CreatePageRequest validation
- PageResponse creation

#### test_use_cases.py
Tests for application use cases:
- CreateArtifactUseCase
- AddPagesUseCase
- RemovePagesUseCase
- UpdateTitleMentionUseCase
- UpdateSummaryCandidateUseCase
- UpdateTagsUseCase
- DeleteArtifactUseCase

### Infrastructure Layer Tests

#### test_infrastructure.py
Tests for infrastructure components:
- PydanticTranscoder for event serialization
- ArtifactProjector and PageProjector for read models
- EventSourcedRepository for persistence
- ReadModelMaterializer

### Integration Tests

#### test_workflows.py
Comprehensive integration tests including:
- Full artifact lifecycle
- Artifact with pages workflow
- Artifact deletion cascade
- Full page lifecycle
- Concurrent operations
- Error recovery
- Data consistency

#### test_edge_cases.py
Edge cases and boundary condition tests:
- Special characters in URIs and filenames
- Long filenames and text
- Order preservation in operations
- Normalization and deduplication
- Multiple deletions
- Many pages and tags
- Event generation sequences
- Boundary conditions

## Running Tests

### Run All Tests
```bash
pytest
```

### Run Tests with Coverage
```bash
pytest --cov=application --cov=domain --cov=infrastructure --cov-report=html
```

### Run Specific Test File
```bash
pytest tests/domain/test_artifact.py
```

### Run Specific Test Class
```bash
pytest tests/domain/test_artifact.py::TestArtifactCreation
```

### Run Specific Test
```bash
pytest tests/domain/test_artifact.py::TestArtifactCreation::test_create_artifact
```

### Run Only Unit Tests
```bash
pytest -m unit
```

### Run Only Integration Tests
```bash
pytest -m integration
```

### Run with Verbose Output
```bash
pytest -v
```

### Run with Detailed Failure Info
```bash
pytest -vv --tb=long
```

## Test Fixtures

### Conftest
The `tests/conftest.py` file provides shared fixtures used across tests:
- `sample_artifact_id`: UUID for artifacts
- `sample_page_id`: UUID for pages
- `sample_artifact`: Artifact aggregate instance
- `sample_page`: Page aggregate instance
- `sample_title_mention`: TitleMention value object
- `sample_summary_candidate`: SummaryCandidate value object
- `sample_compound_mention`: CompoundMention value object
- `sample_tag_mention`: TagMention value object
- `sample_text_mention`: TextMention value object

### Mock Classes
Located in `tests/mocks.py`:
- `MockArtifactRepository`: In-memory artifact repository
- `MockPageRepository`: In-memory page repository
- `MockExternalEventPublisher`: Mock event publisher

## Test Coverage

The test suite covers:

### Domain Layer (100%)
- All aggregate methods
- All value objects
- All domain services
- Event generation
- Business rules and invariants
- Error conditions and edge cases

### Application Layer (100%)
- All use cases
- All mappers
- All DTOs
- Error handling
- External event publishing

### Infrastructure Layer (Partial)
- Serialization/Deserialization
- Event projectors
- Event-sourced repositories
- Read model materialization

### Integration Tests
- Complete workflows
- Cross-layer interactions
- Error recovery
- Data consistency
- Concurrent operations
- Boundary conditions

## Test Patterns

### Arrange-Act-Assert Pattern
Most tests follow the AAA pattern:
```python
def test_something(self):
    # Arrange
    artifact = Artifact.create(...)
    
    # Act
    artifact.update_tags(["tag1"])
    
    # Assert
    assert artifact.tags == ["tag1"]
```

### Using Fixtures
Tests leverage pytest fixtures for common setup:
```python
def test_artifact_update(self, sample_artifact):
    sample_artifact.update_tags(["tag"])
    assert "tag" in sample_artifact.tags
```

### Async Tests
Async use cases are tested with pytest-asyncio:
```python
@pytest.mark.asyncio
async def test_create_artifact(self):
    use_case = CreateArtifactUseCase(repository)
    result = await use_case.execute(request)
    assert isinstance(result, Success)
```

## Continuous Integration

The test suite is designed to run in CI/CD pipelines:
- All tests should pass before merging
- Coverage reports are generated
- Tests run on every commit
- Test results are tracked

## Extending Tests

When adding new features:
1. Add unit tests for new domain logic
2. Add application layer tests for use cases
3. Add integration tests for workflows
4. Update fixtures if new value objects are added
5. Ensure coverage remains > 80%

## Dependencies

Required for testing:
- pytest>=8.3.5
- pytest-asyncio>=0.24.0
- pytest-cov>=4.1.0

Install with:
```bash
pip install -e ".[dev]"
```

## Notes

- All tests are isolated and can run in any order
- Tests use in-memory implementations (no external dependencies)
- Tests are fast and can run frequently during development
- Async tests properly handle event loop lifecycle
"""