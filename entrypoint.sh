#!/bin/bash
set -e

cd /app

# Wait for database to be ready
echo "Waiting for database... "
while ! pg_isready -h ${POSTGRES_HOST:-postgres} -p ${POSTGRES_PORT:-5432} -U ${POSTGRES_USER:-postgres}; do
  sleep 1
done

echo "Database is ready!"

echo "----------APPYING DATABASE MIGRATIONS-------------"
python -m alembic upgrade head

echo "----------INITIALIZE DATABASE------------------"
python initialize_db.py

echo "Starting application..."
# Execute the command passed to the container
exec "$@"