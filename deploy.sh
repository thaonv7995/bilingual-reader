#!/bin/bash
set -e

# Automatically detect the directory where the script is located
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="bilingual-reader"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "============================================="
echo "Starting deployment for Bilingual Book Reader"
echo "Target Directory: $APP_DIR"
echo "============================================="

# 1. Update source code if inside a Git repository
if [ -d "$APP_DIR/.git" ]; then
    echo "Updating repository from GitHub..."
    cd "$APP_DIR"
    git fetch --all
    # Pull latest updates (assumes main branch, or active branch)
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    echo "Pulling latest changes on branch: $CURRENT_BRANCH..."
    git pull origin "$CURRENT_BRANCH"
fi

# 2. Check and install Python 3 if missing
if ! command -v python3 &> /dev/null; then
    echo "Python 3 not found. Installing..."
    sudo apt-get update && sudo apt-get install -y python3
fi

# 3. Ensure server.py is executable
chmod +x "$APP_DIR/server.py"

# 4. Configure systemd service
echo "Configuring systemd service..."
sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=Bilingual Book Reader & AI Proxy Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# 5. Reload systemd daemon and restart service
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Enabling $SERVICE_NAME service..."
sudo systemctl enable "$SERVICE_NAME"

echo "Restarting $SERVICE_NAME service..."
sudo systemctl restart "$SERVICE_NAME"

echo "============================================="
echo "Deployment completed successfully!"
echo "The service is now running on port 27099."
echo "You can check status using: sudo systemctl status $SERVICE_NAME"
echo "============================================="
