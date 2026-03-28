#!/bin/bash
# Start RQ worker for async pipeline tasks
cd "$(dirname "$0")/.."
export REDIS_URL=${REDIS_URL:-"redis://localhost:6379/0"}
rq worker pipeline --url "$REDIS_URL" -v
