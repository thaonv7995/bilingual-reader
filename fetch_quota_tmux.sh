#!/bin/bash
# ==============================================================================
# Dynamic TMUX script to query agy quota with robust screen scraping
# ==============================================================================
SESSION_NAME="agy_quota_fetch_$$"
AGY_BIN="${1:-agy}"

# Clean up any existing session with this name
tmux kill-session -t $SESSION_NAME 2>/dev/null

# Start a new detached tmux session
tmux new-session -d -s $SESSION_NAME -x 120 -y 40 "$AGY_BIN"

# 1. Wait dynamically for the TUI to initialize (max 10 seconds)
for i in {1..20}; do
    pane_content=$(tmux capture-pane -t $SESSION_NAME -p 2>/dev/null || true)
    if [[ "$pane_content" == *"Model"* || "$pane_content" == *"Conversation"* || "$pane_content" == *"Settings"* || "$pane_content" == *"Antigravity"* || "$pane_content" == *"agy"* ]]; then
        break
    fi
    sleep 0.5
done

# 2. Send the "/quota" command
tmux send-keys -t $SESSION_NAME "/quota" C-m

# 3. Wait dynamically for quota data to load on screen (max 10 seconds)
for i in {1..20}; do
    pane_content=$(tmux capture-pane -t $SESSION_NAME -p 2>/dev/null || true)
    if [[ "$pane_content" == *"Account:"* || "$pane_content" == *"Limit"* || "$pane_content" == *"failed"* || "$pane_content" == *"trust"* ]]; then
        break
    fi
    sleep 0.5
done

# 4. Capture the pane content and clean up whitespace
tmux capture-pane -t $SESSION_NAME -p -S - -E - 2>/dev/null | sed '/^[[:space:]]*$/d'

# 5. Clean up the session
tmux kill-session -t $SESSION_NAME 2>/dev/null
