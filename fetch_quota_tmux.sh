#!/bin/bash
SESSION_NAME="agy_quota_fetch"

# Kill any existing session with this name
tmux kill-session -t $SESSION_NAME 2>/dev/null

# Start a new detached tmux session running agy
tmux new-session -d -s $SESSION_NAME -x 1000 -y 100 "agy"

# Wait a moment for agy to load and show the prompt
sleep 4

# Send the "/quota" command and press Enter
tmux send-keys -t $SESSION_NAME "/quota" C-m

# Wait for the quota to be printed
sleep 4

# Capture the current screen output
tmux capture-pane -t $SESSION_NAME -p -S - -E -

# Kill the session
tmux kill-session -t $SESSION_NAME
