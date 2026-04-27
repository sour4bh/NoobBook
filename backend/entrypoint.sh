#!/bin/bash
# Entrypoint for the NoobBook backend container.

set -e

# Ensure runtime data directories exist inside the volume.
mkdir -p data/projects data/tasks data/temp

# Production: use Gunicorn (production WSGI server with gevent for concurrency)
# Development: use Werkzeug dev server (auto-reload, debug mode)
if [ "$FLASK_ENV" = "production" ]; then
    echo "Starting Gunicorn (production)..."
    exec gunicorn -c gunicorn.conf.py "run:app"
else
    echo "Starting Werkzeug dev server..."
    exec python run.py
fi
