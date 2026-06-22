#!/usr/bin/env bash
set -euo pipefail

# Navigate to the workspace directory
cd "/Users/thaonv/Desktop/Books HTML"

echo "=================================================="
echo "Starting processing of 'The Lean Startup'..."
echo "Time: $(date)"
echo "=================================================="

# Run the batch processor with translation and 6 threads
PYTHONPATH=application/backend application/.venv/bin/python3 -u application/backend/scripts/batch_processor.py --book books/the-lean-startup-erick-ries --translate --threads 6 --provider antigravity

echo "=================================================="
echo "Processing complete!"
echo "Time: $(date)"
echo "=================================================="
