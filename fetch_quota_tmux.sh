#!/bin/bash
SESSION_NAME="agy_quota_fetch_$$"

AGY_BIN="${1:-agy}"

# Kill any existing session with this name just in case
tmux kill-session -t $SESSION_NAME 2>/dev/null

# Start a new detached tmux session running agy in current directory
tmux new-session -d -s $SESSION_NAME -x 1000 -y 100 "$AGY_BIN"

# Wait a moment for agy to load
sleep 3

# Send the "/quota" command and press Enter
tmux send-keys -t $SESSION_NAME "/quota" C-m

# Wait for the quota to be printed
sleep 3

# Capture the current screen output
tmux capture-pane -t $SESSION_NAME -p -S - -E - | sed '/^[[:space:]]*$/d'

# Kill the session
tmux kill-session -t $SESSION_NAME
