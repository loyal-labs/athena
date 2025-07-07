#!/bin/bash
set -e

echo "Starting Athena application..."

# Wait for database connection
echo "Checking database connection..."
uv run python scripts/run_migrations.py

if [ $? -eq 0 ]; then
    echo "Database is ready"
else
    echo "Database connection failed, exiting..."
    exit 1
fi

# Run database migrations
echo "Running database migrations..."
uv run alembic upgrade head

if [ $? -eq 0 ]; then
    echo "Migrations completed successfully"
else
    echo "Migration failed, exiting..."
    exit 1
fi

# Start the application
echo "Starting FastAPI application..."
exec uv run uvicorn app:app --host 0.0.0.0 --port 8000 --reload --loop uvloop