#!/bin/bash
# ==============================================================================
# Books HTML Web Studio Installer, Updater, and Uninstaller
# ==============================================================================
set -e

# Configuration
GITHUB_REPO="thaonv7995/bilingual-reader"
APP_NAME="books-studio"

# Determine installation directory based on privilege
if [ "$EUID" -eq 0 ]; then
    INSTALL_DIR="/opt/$APP_NAME"
    BIN_DIR="/usr/local/bin"
else
    INSTALL_DIR="$HOME/.local/share/$APP_NAME"
    BIN_DIR="$HOME/.local/bin"
fi

# Color helpers
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

show_usage() {
    echo "Usage: install.sh [options]"
    echo "Options:"
    echo "  --install      Install the application (default)"
    echo "  --update       Update the installed application"
    echo "  --uninstall    Uninstall the application"
    echo "  --help         Show this help message"
}

# Parse options
MODE="install"
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --install) MODE="install" ;;
        --update) MODE="update" ;;
        --uninstall|--remove) MODE="uninstall" ;;
        --help|-h) show_usage; exit 0 ;;
        *) echo "Unknown option: $1"; show_usage; exit 1 ;;
    esac
    shift
done

install_dependencies() {
    echo -e "\n${BLUE}=== Installing OS Dependencies ===${NC}"
    if [ "$EUID" -eq 0 ]; then
        apt-get update && apt-get install -y expect tmux python3-pip python3-venv python3-dev build-essential curl git
    else
        if command -v sudo >/dev/null 2>&1; then
            echo -e "${YELLOW}Requesting sudo permissions to install dependencies (expect, tmux, python3)...${NC}"
            sudo apt-get update && sudo apt-get install -y expect tmux python3-pip python3-venv python3-dev build-essential curl git
        else
            echo -e "${RED}[✘] Error: sudo is required to install dependencies but not found.${NC}"
            echo -e "Please install 'expect', 'tmux', 'python3-venv', 'python3-pip', 'build-essential' manually."
            exit 1
        fi
    fi
}

get_latest_release_url() {
    # Fetch the latest release tag and download url from GitHub api
    local release_json
    release_json=$(curl -s "https://api.github.com/repos/$GITHUB_REPO/releases/latest")
    
    # Extract asset download URL for tarball
    local download_url
    download_url=$(echo "$release_json" | grep "browser_download_url" | grep ".tar.gz" | head -n 1 | cut -d '"' -f 4)
    
    if [ -z "$download_url" ]; then
        # Fallback to main branch archive if no release assets exist yet
        echo -e "${YELLOW}[!] No release asset found. Falling back to repository main branch archive...${NC}"
        download_url="https://github.com/$GITHUB_REPO/archive/refs/heads/main.tar.gz"
    fi
    echo "$download_url"
}

stop_existing_server() {
    echo -e "\n${BLUE}=== Stopping Existing Instances ===${NC}"
    if [ "$EUID" -eq 0 ] && [ -f /etc/systemd/system/books-studio.service ]; then
        echo "Stopping systemd service..."
        systemctl stop books-studio 2>/dev/null || true
    else
        if [ -f "$INSTALL_DIR/books-studio.pid" ]; then
            local pid
            pid=$(cat "$INSTALL_DIR/books-studio.pid")
            if kill -0 "$pid" 2>/dev/null; then
                echo "Stopping background process (PID: $pid)..."
                kill "$pid" 2>/dev/null || true
                sleep 1
            fi
            rm -f "$INSTALL_DIR/books-studio.pid"
        fi
        pkill -u "$USER" -f "books-cli serve" 2>/dev/null || true
    fi
}

do_install() {
    echo -e "${BLUE}=== Starting Installation ===${NC}"
    echo -e "Target Directory: ${GREEN}$INSTALL_DIR${NC}"
    echo -e "Executable Link:  ${GREEN}$BIN_DIR/$APP_NAME${NC}"

    # 1. Install system packages
    install_dependencies

    # 2. Stop any running server
    stop_existing_server

    # 3. Download and extract
    echo -e "\n${BLUE}=== Downloading Application Code ===${NC}"
    local download_url
    download_url=$(get_latest_release_url)
    echo -e "Downloading from: ${GREEN}$download_url${NC}"
    
    mkdir -p "$INSTALL_DIR"
    local temp_tar="/tmp/$APP_NAME-latest.tar.gz"
    curl -L "$download_url" -o "$temp_tar"
    
    echo -e "Extracting archive to target directory..."
    # Preserve user books directory if updating
    if [ -d "$INSTALL_DIR/books" ]; then
        rm -rf "/tmp/$APP_NAME-books-backup"
        mv "$INSTALL_DIR/books" "/tmp/$APP_NAME-books-backup"
    fi
    # Preserve credentials if updating
    if [ -f "$INSTALL_DIR/.credentials" ]; then
        cp "$INSTALL_DIR/.credentials" "/tmp/$APP_NAME-credentials-backup"
    fi
    
    # Extract tarball
    rm -rf "$INSTALL_DIR"/{application,.cursor,*.exp,fetch_quota_tmux.sh} 2>/dev/null || true
    tar -xzf "$temp_tar" -C "$INSTALL_DIR" --strip-components=1 || tar -xzf "$temp_tar" -C "$INSTALL_DIR"
    
    # Restore books directory if backed up
    if [ -d "/tmp/$APP_NAME-books-backup" ]; then
        rm -rf "$INSTALL_DIR/books"
        mv "/tmp/$APP_NAME-books-backup" "$INSTALL_DIR/books"
    fi
    # Restore credentials if backed up
    if [ -f "/tmp/$APP_NAME-credentials-backup" ]; then
        mv "/tmp/$APP_NAME-credentials-backup" "$INSTALL_DIR/.credentials"
    fi
    
    # Cleanup temp tar
    rm -f "$temp_tar"

    # 4. Setup Python venv and install
    echo -e "\n${BLUE}=== Configuring Virtual Environment ===${NC}"
    local venv_path="$INSTALL_DIR/application/.venv"
    python3 -m venv "$venv_path"
    "$venv_path/bin/pip" install --upgrade pip
    
    if [ -f "$INSTALL_DIR/application/backend/requirements.txt" ]; then
        "$venv_path/bin/pip" install -r "$INSTALL_DIR/application/backend/requirements.txt"
    fi
    "$venv_path/bin/pip" install -e "$INSTALL_DIR/application/backend"

    # Make utility scripts executable
    chmod +x "$INSTALL_DIR"/*.exp "$INSTALL_DIR"/*.sh "$INSTALL_DIR"/application/backend/books_cli/bin/* 2>/dev/null || true

    # 5. Generate / Load Credentials
    local creds_file="$INSTALL_DIR/.credentials"
    local username="admin"
    local password
    local session_token
    
    if [ -f "$creds_file" ]; then
        echo -e "Loading existing credentials..."
        # Extract variables from credentials file manually to avoid shell execution limits
        username=$(grep STUDIO_USERNAME "$creds_file" | cut -d'"' -f2)
        password=$(grep STUDIO_PASSWORD "$creds_file" | cut -d'"' -f2)
        session_token=$(grep STUDIO_SESSION_TOKEN "$creds_file" | cut -d'"' -f2)
    else
        echo -e "Generating random credentials..."
        password=$(python3 -c "import secrets; print(secrets.token_urlsafe(12))")
        session_token=$(python3 -c "import secrets; print(secrets.token_hex(24))")
        cat << EOF > "$creds_file"
export STUDIO_USERNAME="$username"
export STUDIO_PASSWORD="$password"
export STUDIO_SESSION_TOKEN="$session_token"
EOF
        chmod 600 "$creds_file"
    fi

    # 6. Create Control / Launcher Wrapper
    echo -e "\n${BLUE}=== Creating Executable Wrapper ===${NC}"
    mkdir -p "$BIN_DIR"
    local wrapper_path="$INSTALL_DIR/run_studio.sh"
    
    # Detect if systemd should be configured
    local using_systemd=false
    if [ "$EUID" -eq 0 ] && command -v systemctl >/dev/null 2>&1; then
        using_systemd=true
    fi

    cat << EOF > "$wrapper_path"
#!/bin/bash
# Wrapper to control Books HTML Studio (start/stop/status/restart)
export BOOKS_STUDIO_ROOT="$INSTALL_DIR"
export PATH="$INSTALL_DIR/application/backend/books_cli/bin:\$PATH"
if [ -f "$INSTALL_DIR/.credentials" ]; then
    source "$INSTALL_DIR/.credentials"
fi

PID_FILE="$INSTALL_DIR/books-studio.pid"
LOG_FILE="$INSTALL_DIR/books-studio.log"
VENV_BIN="$INSTALL_DIR/application/.venv/bin/books-cli"
USING_SYSTEMD=$using_systemd

stop_service() {
    if \$USING_SYSTEMD; then
        echo "Stopping books-studio systemd service..."
        systemctl stop books-studio 2>/dev/null || true
    else
        if [ -f "\$PID_FILE" ]; then
            local pid
            pid=\$(cat "\$PID_FILE")
            if kill -0 "\$pid" 2>/dev/null; then
                echo "Stopping books-studio process (PID: \$pid)..."
                kill "\$pid" 2>/dev/null || true
                sleep 1
            fi
            rm -f "\$PID_FILE"
        fi
        pkill -u "\$USER" -f "books-cli serve" 2>/dev/null || true
    fi
}

start_service() {
    if \$USING_SYSTEMD; then
        echo "Starting books-studio systemd service..."
        systemctl start books-studio
    else
        if [ -f "\$PID_FILE" ]; then
            local pid
            pid=\$(cat "\$PID_FILE")
            if kill -0 "\$pid" 2>/dev/null; then
                echo "books-studio is already running (PID: \$pid)."
                return
            fi
        fi
        echo "Starting books-studio in background..."
        nohup "\$VENV_BIN" serve > "\$LOG_FILE" 2>&1 &
        echo \$! > "\$PID_FILE"
        sleep 2
    fi
}

status_service() {
    if \$USING_SYSTEMD; then
        systemctl status books-studio
    else
        if [ -f "\$PID_FILE" ]; then
            local pid
            pid=\$(cat "\$PID_FILE")
            if kill -0 "\$pid" 2>/dev/null; then
                echo "books-studio is running (PID: \$pid)"
                return 0
            fi
        fi
        echo "books-studio is stopped."
        return 1
    fi
}

case "\$1" in
    stop|--stop)
        stop_service
        ;;
    start|--start)
        start_service
        ;;
    restart|--restart)
        stop_service
        start_service
        ;;
    status|--status)
        status_service
        ;;
    update|--update)
        if [ -f "$INSTALL_DIR/install.sh" ]; then
            echo "Running local install.sh with --update..."
            bash "$INSTALL_DIR/install.sh" --update
        else
            echo "Downloading and running latest installer..."
            curl -fsSL https://raw.githubusercontent.com/$GITHUB_REPO/main/install.sh | bash -s -- --update
        fi
        ;;
    uninstall|--uninstall)
        if [ -f "$INSTALL_DIR/install.sh" ]; then
            bash "$INSTALL_DIR/install.sh" --uninstall
        else
            stop_service
            echo "Removing installation folder at $INSTALL_DIR..."
            rm -rf "$INSTALL_DIR"
            echo "Removing symlink..."
            rm -f "$BIN_DIR/$APP_NAME"
            echo "Uninstalled."
        fi
        ;;
    *)
        # Default behavior: run in foreground
        exec "\$VENV_BIN" serve "\$@"
        ;;
esac
EOF
    chmod +x "$wrapper_path"
    
    # Remove old symlink and create new one
    rm -f "$BIN_DIR/$APP_NAME"
    ln -s "$wrapper_path" "$BIN_DIR/$APP_NAME"

    # 7. Setup Daemon (systemd or background)
    local service_type=""
    local run_pid=""
    if $using_systemd; then
        echo -e "\n${BLUE}=== Configuring systemd Service ===${NC}"
        service_type="systemd"
        SERVICE_USER=${SUDO_USER:-root}
        if [ "$SERVICE_USER" = "root" ]; then
            SERVICE_HOME="/root"
        else
            SERVICE_HOME=$(eval echo ~$SERVICE_USER)
        fi
        cat << EOF > /etc/systemd/system/books-studio.service
[Unit]
Description=Books HTML Web Studio
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=HOME=$SERVICE_HOME
Environment=BOOKS_STUDIO_ROOT=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/application/backend/books_cli/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=$INSTALL_DIR/run_studio.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl enable books-studio
        systemctl restart books-studio
        run_pid=$(systemctl show -p MainPID books-studio | cut -d= -f2)
    else
        echo -e "\n${BLUE}=== Starting Service in Background ===${NC}"
        service_type="background process"
        "$wrapper_path" --start
        if [ -f "$INSTALL_DIR/books-studio.pid" ]; then
            run_pid=$(cat "$INSTALL_DIR/books-studio.pid")
        fi
    fi

    # Retrieve Host IP
    local local_ip
    local_ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [ -z "$local_ip" ]; then
        local_ip="127.0.0.1"
    fi

    # 8. Render Summary Report Table
    echo -e "\n${GREEN}[✔] Installation completed successfully!${NC}"
    echo -e "${BLUE}=================================================================${NC}"
    echo -e "                   BOOKS HTML WEB STUDIO SUMMARY                 "
    echo -e "${BLUE}=================================================================${NC}"
    printf "  %-18s : %s\n" "Status" "RUNNING (PID: $run_pid)"
    printf "  %-18s : %s\n" "Daemon Type" "$service_type"
    printf "  %-18s : %s\n" "Studio Web URL" "http://$local_ip:8765"
    printf "  %-18s : %s\n" "Login Username" "$username"
    printf "  %-18s : %s\n" "Login Password" "$password"
    printf "  %-18s : %s\n" "Session Token" "$session_token"
    printf "  %-18s : %s\n" "Install Path" "$INSTALL_DIR"
    printf "  %-18s : %s\n" "Command Utility" "$BIN_DIR/$APP_NAME"
    echo -e "${BLUE}=================================================================${NC}"
    echo -e "  To manage the background service, you can run:"
    echo -e "    * Stop:    ${YELLOW}$APP_NAME --stop${NC}"
    echo -e "    * Start:   ${YELLOW}$APP_NAME --start${NC}"
    echo -e "    * Restart: ${YELLOW}$APP_NAME --restart${NC}"
    echo -e "    * Status:  ${YELLOW}$APP_NAME --status${NC}"
    echo -e "${BLUE}=================================================================${NC}\n"
}

do_update() {
    echo -e "${BLUE}=== Starting Update ===${NC}"
    if [ ! -d "$INSTALL_DIR" ]; then
        echo -e "${RED}[✘] Error: $APP_NAME is not installed yet. Run install instead.${NC}"
        exit 1
    fi
    do_install
}

do_uninstall() {
    echo -e "${RED}=== Starting Uninstallation ===${NC}"
    read -p "Are you sure you want to completely uninstall $APP_NAME? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi

    # Stop and remove daemon
    stop_existing_server
    
    if [ "$EUID" -eq 0 ] && [ -f /etc/systemd/system/books-studio.service ]; then
        echo "Removing systemd service..."
        systemctl disable books-studio 2>/dev/null || true
        rm -f /etc/systemd/system/books-studio.service
        systemctl daemon-reload
    fi

    echo "Removing installation folder at $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR"
    
    echo "Removing symlink at $BIN_DIR/$APP_NAME..."
    rm -f "$BIN_DIR/$APP_NAME"

    echo -e "${GREEN}[✔] $APP_NAME uninstalled successfully.${NC}"
}

# Main execution router
case "$MODE" in
    install)   do_install ;;
    update)    do_update ;;
    uninstall) do_uninstall ;;
esac
