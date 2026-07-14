#!/bin/bash
# ==============================================================================
# Setup script for Books HTML Web Studio on Debian/Ubuntu
# ==============================================================================
set -e

# Color output helpers
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Setup Books HTML Web Studio for Debian/Ubuntu ===${NC}\n"

# 1. Check OS
if [ -f /etc/debian_version ]; then
    echo -e "${GREEN}[✔] Debian/Ubuntu system detected.${NC}"
else
    echo -e "${YELLOW}[!] Warning: This script is designed for Debian/Ubuntu systems.${NC}"
    read -p "Do you want to continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 2. Check and Install OS Packages
echo -e "\n${BLUE}--- Step 1: Installing system packages (expect, tmux, python3) ---${NC}"
echo -e "${YELLOW}This requires sudo privileges. You might be prompted for your password.${NC}"

# Check for apt-get
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y expect tmux python3-pip python3-venv python3-dev build-essential chromium
    echo -e "${GREEN}[✔] System packages installed successfully.${NC}"
else
    echo -e "${RED}[✘] apt-get not found. Please install expect, tmux, python3-pip, python3-venv manually.${NC}"
    exit 1
fi

# 3. Create Python Virtual Environment
echo -e "\n${BLUE}--- Step 2: Creating Python virtual environment ---${NC}"
VENV_DIR="application/.venv"

if [ -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}[!] Virtual environment already exists at $VENV_DIR.${NC}"
    read -p "Do you want to recreate it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$VENV_DIR"
        python3 -m venv "$VENV_DIR"
        echo -e "${GREEN}[✔] Virtual environment recreated.${NC}"
    else
        echo -e "${GREEN}[✔] Using existing virtual environment.${NC}"
    fi
else
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}[✔] Virtual environment created at $VENV_DIR.${NC}"
fi

# 4. Install Python Dependencies
echo -e "\n${BLUE}--- Step 3: Installing Python packages ---${NC}"
"$VENV_DIR/bin/pip" install --upgrade pip
if [ -f "application/backend/requirements.txt" ]; then
    "$VENV_DIR/bin/pip" install -r application/backend/requirements.txt
fi
"$VENV_DIR/bin/pip" install -e application/backend
echo -e "${GREEN}[✔] Python packages installed successfully.${NC}"

# 5. Create start script
echo -e "\n${BLUE}--- Step 4: Creating runner script ---${NC}"
cat << 'EOF' > run_studio.sh
#!/bin/bash
# Script to start Books HTML Studio
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$SCRIPT_DIR/application/backend/books_cli/bin:$PATH"
echo "Starting Books HTML Web Studio..."
"$SCRIPT_DIR/application/.venv/bin/books-cli" serve "$@"
EOF
chmod +x run_studio.sh
echo -e "${GREEN}[✔] Created './run_studio.sh'. You can run this script to start the studio.${NC}"

# 6. Inform user about AGY CLI
echo -e "\n${BLUE}--- Step 5: Verification and Final Notes ---${NC}"
if command -v agy >/dev/null 2>&1; then
    echo -e "${GREEN}[✔] Antigravity CLI (agy) binary detected in PATH.${NC}"
else
    echo -e "${YELLOW}[!] Note: Antigravity CLI (agy) was not found in your PATH.${NC}"
    echo -e "    Please ensure 'agy' is installed on your Debian system."
    echo -e "    You can add it to your user bin directory, e.g. '~/.local/bin/agy'."
fi

echo -e "\n${GREEN}Setup completed successfully!${NC}"
echo -e "To start the studio, simply execute:"
echo -e "  ${BLUE}./run_studio.sh${NC}"
echo
