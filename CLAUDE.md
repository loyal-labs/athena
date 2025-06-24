# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Athena is a Telegram bot application built with FastAPI and Kurigram (Pyrogram fork) that integrates AI capabilities through Google Vertex AI. The application uses an event-driven architecture with dependency injection and follows async patterns throughout.

## Key Technologies

- **Language**: Python 3.12
- **Package Manager**: UV (not pip/poetry)
- **Web Framework**: FastAPI with Uvicorn
- **Telegram**: Kurigram (Pyrogram fork)
- **Database**: PostgreSQL with SQLAlchemy/SQLModel
- **AI/LLM**: Google Vertex AI, Gemini models, Pydantic AI
- **Secrets**: 1Password SDK
- **Deployment**: Google App Engine

## Development Commands

```bash
# Install dependencies
uv sync

# Run development server
uv run uvicorn app:app --reload

# Run with Docker
./run.sh

# Start PostgreSQL (local development)
docker compose up -d

# Run tests
uv run pytest

# Type checking
uv run pyright

# Linting
uv run ruff check .
uv run ruff format .

# Run a single test
uv run pytest path/to/test_file.py::TestClass::test_method -v
```

## Architecture Overview

### Service Architecture
The application uses dependency injection with a central Container that manages all services:

- **Event Bus** (`src/shared/bus.py`): Central communication between services using publish/subscribe pattern
- **Services** are injected and communicate through events, not direct calls
- Each service is a singleton managed by the dependency-injector Container

### Directory Structure
- `/src/api/`: FastAPI router endpoints
- `/src/shared/`: Core utilities and shared services
  - `database.py`: Database connection and session management
  - `cache.py`: Disk-based caching implementation
  - `bus.py`: Event bus for service communication
  - `logging.py`: Structured logging setup
  - `secrets.py`: 1Password integration for secrets
- `/src/telegram/`: Telegram bot functionality
  - `agents/`: AI-powered response agents using Pydantic AI
  - `business/`: Business logic for Telegram operations
  - `kurigram.py`: Main Telegram client service
- `/src/telegraph/`: Telegraph API integration
- `/src/telemetree/`: Posts service integration

### Key Patterns

1. **Async Everywhere**: All database operations, API calls, and service methods use async/await
2. **Event-Driven**: Services publish events to the bus instead of calling each other directly
3. **Dependency Injection**: Services are wired through the Container in `app.py`
4. **Type Safety**: Extensive use of Pydantic models and type hints throughout

### Database Operations
- Uses SQLModel (SQLAlchemy + Pydantic) for ORM
- All database operations are async using asyncpg
- Sessions are managed through dependency injection
- Models are defined with SQLModel in respective service modules

### Environment Configuration
- Uses 1Password SDK for production secrets
- Environment variables are loaded from `.env` for local development
- Key variables: `DATABASE_URL`, `TELEGRAM_*`, `GOOGLE_CLOUD_*`, `OP_*`

### Testing Approach
- pytest with pytest-asyncio for async tests
- Tests should mock external services (Telegram, database, etc.)
- Use fixtures for common test setup
- Run focused tests with: `uv run pytest path/to/test::test_name -v`

## Important Considerations

1. **UV Package Manager**: Always use `uv` commands, not `pip` or `poetry`
2. **Async Context**: Remember to use `async`/`await` for all I/O operations
3. **Event Bus**: When adding new features, consider using events for loose coupling
4. **Type Hints**: Maintain type hints for all function signatures
5. **Service Pattern**: New features should be implemented as services in the Container
6. **Database Sessions**: Always use injected database sessions, never create directly
7. **Secrets Management**: Use the secrets service for any sensitive configuration