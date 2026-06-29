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

do_install() {
    echo -e "${BLUE}=== Starting Installation ===${NC}"
    echo -e "Target Directory: ${GREEN}$INSTALL_DIR${NC}"
    echo -e "Executable Link:  ${GREEN}$BIN_DIR/$APP_NAME${NC}"

    # 1. Install system packages
    install_dependencies

    # 2. Download and extract
    echo -e "\n${BLUE}=== Downloading Application Code ===${NC}"
    local download_url
    download_url=$(get_latest_release_url)
    echo -e "Downloading from: ${GREEN}$download_url${NC}"
    
    mkdir -p "$INSTALL_DIR"
    local temp_tar="/tmp/$APP_NAME-latest.tar.gz"
    curl -L "$download_url" -o "$temp_tar"
    
    echo -e "Extracting archive to target directory..."
    # Clear directory but preserve user books directory if updating
    if [ -d "$INSTALL_DIR/books" ]; then
        mv "$INSTALL_DIR/books" "/tmp/$APP_NAME-books-backup"
    fi
    
    # Extract tarball
    rm -rf "$INSTALL_DIR"/{application,*.exp,fetch_quota_tmux.sh} 2>/dev/null || true
    tar -xzf "$temp_tar" -C "$INSTALL_DIR" --strip-components=1 || tar -xzf "$temp_tar" -C "$INSTALL_DIR"
    
    # Restore books directory if backed up
    if [ -d "/tmp/$APP_NAME-books-backup" ]; then
        rm -rf "$INSTALL_DIR/books"
        mv "/tmp/$APP_NAME-books-backup" "$INSTALL_DIR/books"
    fi
    
    # Cleanup temp tar
    rm -f "$temp_tar"

    # 3. Setup Python venv and install
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

    # 4. Create launcher symlink
    echo -e "\n${BLUE}=== Creating Executable Wrapper ===${NC}"
    mkdir -p "$BIN_DIR"
    local wrapper_path="$INSTALL_DIR/run_studio.sh"
    
    cat << EOF > "$wrapper_path"
#!/bin/bash
export BOOKS_STUDIO_ROOT="$INSTALL_DIR"
export PATH="$INSTALL_DIR/application/backend/books_cli/bin:\$PATH"
exec "$venv_path/bin/books-cli" serve "\$@"
EOF
    chmod +x "$wrapper_path"
    
    # Remove old symlink if exists
    rm -f "$BIN_DIR/$APP_NAME"
    ln -s "$wrapper_path" "$BIN_DIR/$APP_NAME"

    # Adjust path if user local bin directory is not in PATH
    if [ "$EUID" -ne 0 ] && [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        echo -e "${YELLOW}[!] Warning: $HOME/.local/bin is not in your PATH environment variable.${NC}"
        echo -e "    Please add this line to your ~/.bashrc or ~/.zshrc file:"
        echo -e "    ${BLUE}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
    fi

    echo -e "\n${GREEN}[✔] $APP_NAME installed successfully!${NC}"
    echo -e "To start the studio, run:"
    echo -e "  ${BLUE}$APP_NAME${NC}"
    echo
}

do_update() {
    echo -e "${BLUE}=== Starting Update ===${NC}"
    if [ ! -d "$INSTALL_DIR" ]; then
        echo -e "${RED}[✘] Error: $APP_NAME is not installed yet. Run install instead.${NC}"
        exit 1
    fi
    do_install
    echo -e "${GREEN}[✔] $APP_NAME updated successfully!${NC}"
}

do_uninstall() {
    echo -e "${RED}=== Starting Uninstallation ===${NC}"
    read -p "Are you sure you want to completely uninstall $APP_NAME? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi

    # Kill any running books-cli serve processes first
    echo "Stopping any active instances..."
    pkill -f "books-cli serve" || true

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
