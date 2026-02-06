"""Quick Reference Guide - Test Suite

## File Structure

```
tests/
├── conftest.py                          # Shared fixtures
├── mocks.py                             # Mock implementations
├── pytest.ini                           # Pytest configuration
├── domain/
│   ├── __init__.py
│   ├── test_artifact.py                 # 33 tests for Artifact aggregate
│   ├── test_page.py                     # 29 tests for Page aggregate
│   ├── test_value_objects.py            # 21 tests for value objects
│   └── test_services.py                 # 5 tests for domain services
├── application/
│   ├── __init__.py
│   ├── test_mappers.py                  # 10 tests for mappers
│   ├── test_dtos.py                     # 11 tests for DTOs
│   └── test_use_cases.py                # 19 tests for use cases
├── infrastructure/
│   ├── __init__.py
│   └── test_infrastructure.py           # 8 tests for infrastructure
├── integration/
│   ├── __init__.py
│   ├── test_workflows.py                # 7 tests for complete workflows
│   └── test_edge_cases.py               # 24 tests for edge cases
└── interfaces/
    ├── __init__.py
    └── test_api_routes.py               # 20 tests for API routes
```

## Running Tests

### Quick Start
```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov
```

### By Layer
```bash
# Domain layer only
pytest tests/domain -v

# Application layer only
pytest tests/application -v

# Infrastructure layer only
pytest tests/infrastructure -v

# Integration tests only
pytest tests/integration -v

# API tests only
pytest tests/interfaces -v
```

### Specific Tests
```bash
# Run single test file
pytest tests/domain/test_artifact.py

# Run single test class
pytest tests/domain/test_artifact.py::TestArtifactCreation

# Run single test
pytest tests/domain/test_artifact.py::TestArtifactCreation::test_create_artifact

# Run tests matching pattern
pytest -k "artifact" -v

# Run tests matching multiple patterns
pytest -k "artifact or page" -v
```

### Advanced
```bash
# Run with coverage and HTML report
pytest --cov --cov-report=html

# Run tests that failed last time
pytest --lf

# Run tests with specific marker
pytest -m "not slow"

# Run tests in parallel (requires pytest-xdist)
pytest -n auto

# Run with detailed output
pytest -vv --tb=long

# Stop on first failure
pytest -x

# Stop after N failures
pytest --maxfail=3
```

## Test Organization

### Domain Tests (88 tests)
- Artifact aggregate creation, updates, deletion
- Page aggregate creation, updates, deletion
- Value objects (TitleMention, SummaryCandidate, etc.)
- Domain services (ArtifactDeletionService)
- Event generation and sourcing

### Application Tests (40 tests)
- Use cases (Create, Update, Delete operations)
- Mappers (Artifact → ArtifactResponse, Page → PageResponse)
- DTOs (Data validation and transformation)
- Error handling and result types

### Infrastructure Tests (8 tests)
- Event serialization/deserialization
- Event projectors for read models
- Event-sourced repositories
- Read model materialization

### Integration Tests (31 tests)
- Complete workflows (create → update → delete)
- Cross-layer interactions
- Error recovery scenarios
- Data consistency
- Edge cases and boundary conditions

### API Tests (20 tests)
- REST endpoints (GET, POST, PUT, DELETE)
- Request validation
- Response formatting
- Error handling
- Status codes

## Key Testing Patterns

### Using Fixtures
```python
def test_update_artifact(self, sample_artifact):
    # sample_artifact is injected by pytest
    sample_artifact.update_tags(["tag"])
    assert "tag" in sample_artifact.tags
```

### Testing Async Use Cases
```python
@pytest.mark.asyncio
async def test_create_artifact(self):
    use_case = CreateArtifactUseCase(repository)
    result = await use_case.execute(request)
    assert isinstance(result, Success)
```

### Testing Error Cases
```python
def test_delete_deleted_artifact_raises_error(self):
    artifact = sample_artifact()
    artifact.delete()
    
    with pytest.raises(ValueError):
        artifact.delete()
```

### Testing with Mocks
```python
def test_save_calls_repository(self):
    repo = MockArtifactRepository()
    artifact = Artifact.create(...)
    repo.save(artifact)
    
    assert repo.save_called is True
```

## Common Commands

```bash
# Install test dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov

# Run specific test file
pytest tests/domain/test_artifact.py

# Run tests with keyword matching
pytest -k "test_create"

# Run tests with markers
pytest -m "not slow"

# Run failed tests
pytest --lf

# Run tests in verbose mode
pytest -v

# Run with short traceback
pytest --tb=short

# Run and stop on first failure
pytest -x

# Run N tests at a time
pytest --maxfail=3
```

## Fixtures Available

From `tests/conftest.py`:
- `sample_artifact_id` - UUID for testing
- `sample_page_id` - UUID for testing
- `sample_artifact` - Artifact aggregate instance
- `sample_page` - Page aggregate instance
- `sample_title_mention` - TitleMention value object
- `sample_summary_candidate` - SummaryCandidate value object
- `sample_compound_mention` - CompoundMention value object
- `sample_tag_mention` - TagMention value object
- `sample_text_mention` - TextMention value object

## Mocks Available

From `tests/mocks.py`:
- `MockArtifactRepository` - In-memory artifact repository
- `MockPageRepository` - In-memory page repository
- `MockExternalEventPublisher` - Mock event publisher

## Test Statistics

- **Total Tests:** 187+
- **Total Lines of Test Code:** 2000+
- **Coverage:** ~80%
- **Test Execution Time:** < 5 seconds

## Common Issues & Solutions

### Issue: Import errors in tests
**Solution:** Ensure project root is in PYTHONPATH
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Issue: Async test not running
**Solution:** Install pytest-asyncio and use @pytest.mark.asyncio decorator
```bash
pip install pytest-asyncio
```

### Issue: Fixtures not found
**Solution:** Ensure conftest.py is in the correct directory
- conftest.py should be at `tests/conftest.py`

### Issue: Import from interfaces fails
**Solution:** Ensure interfaces module is properly initialized
- Check that `interfaces/__init__.py` exists


## References

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio)
- [FastAPI Testing](https://fastapi.tiangolo.com/advanced/testing-dependencies/)
- [Returns Library](https://github.com/dry-python/returns)
- [Eventsourcing](https://eventsourcing.readthedocs.io/)
"""