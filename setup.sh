#!/bin/bash

set -e  # Exit immediately if a command exits with a non-zero status

# Colors for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${BLUE}${BOLD}Arcadia Agent Management Tool${NC}"
echo "========================================"

# Function to detect GPU hardware
detect_gpu() {
    echo -e "${YELLOW}Detecting hardware configuration...${NC}"
    
    # Check if nvidia-smi is available
    if command -v nvidia-smi &> /dev/null; then
        echo -e "${GREEN}NVIDIA GPU detected.${NC}"
        return 1
    fi
    
    # Check for AMD GPUs using rocm-smi
    if command -v rocm-smi &> /dev/null; then
        echo -e "${GREEN}AMD GPU (ROCm) detected.${NC}"
        return 2
    fi
    
    # If no GPU detected, use CPU
    echo -e "${YELLOW}No GPU detected, using CPU configuration.${NC}"
    return 0
}

# Create requirements files for different hardware
create_requirement_files() {
    # Create Requirements directory if it doesn't exist
    mkdir -p Requirements
    
    # Simply copy the base requirements file to the hardware-specific ones.
    cp Requirements/requirements.txt Requirements/requirements.cpu.txt
    cp Requirements/requirements.txt Requirements/requirements.nvidia.txt
    cp Requirements/requirements.txt Requirements/requirements.amd.txt
}

# Clean up unnecessary files and folders
cleanup() {
    echo -e "${YELLOW}Cleaning up project structure...${NC}"
    
    # Remove old virtual environments
    rm -rf new_venv .venv_snapshot_* 2>/dev/null || true
    
    # Remove temporary files
    find . -name "*.tmp" -type f -delete
    
    # Clean up legacy lowercase directories and config files if present
    if [ -d "config" ] || [ -f "projects.config" ]; then
        echo -e "${YELLOW}Legacy configuration files detected.${NC}"
        read -p "Would you like to remove old lowercase directories (config) and config files? (y/n): " clean_legacy
        if [[ $clean_legacy =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}Removing legacy configuration files...${NC}"
            [ -d "config" ] && rm -rf config
            [ -f "projects.config" ] && rm -f projects.config
            echo -e "${GREEN}Legacy configuration removed.${NC}"
        fi
    fi
    
    # Ensure uppercase directory structure for Config, Core, Tools, Output, and Clients
    mkdir -p Config Core Tools Output Clients Docs Scheduler Requirements
    
    echo -e "${GREEN}Cleanup complete.${NC}"
}

# Setup virtual environment and install dependencies
setup_environment() {
    local gpu_type=$1
    local skip_venv=$2
    
    echo -e "${YELLOW}Setting up virtual environment...${NC}"
    
    if [ "$skip_venv" = false ] && [ -d ".venv" ]; then
        echo -e "${YELLOW}Removing existing virtual environment...${NC}"
        rm -rf .venv
        
        # Create new virtual environment
        python -m venv .venv
        source .venv/bin/activate
        python -m pip install --upgrade pip
        
        case $gpu_type in
            0)
                echo -e "${YELLOW}Installing CPU dependencies...${NC}"
                pip install -r Requirements/requirements.cpu.txt
                ;;
            1)
                echo -e "${YELLOW}Installing NVIDIA GPU dependencies...${NC}"
                pip install -r Requirements/requirements.nvidia.txt
                ;;
            2)
                echo -e "${YELLOW}Installing AMD GPU dependencies...${NC}"
                pip install -r Requirements/requirements.amd.txt
                ;;
        esac
    elif [ -d ".venv" ]; then
        echo -e "${GREEN}Using existing virtual environment.${NC}"
        source .venv/bin/activate
    else
        python -m venv .venv
        source .venv/bin/activate
        python -m pip install --upgrade pip
        
        case $gpu_type in
            0)
                echo -e "${YELLOW}Installing CPU dependencies...${NC}"
                pip install -r Requirements/requirements.cpu.txt
                ;;
            1)
                echo -e "${YELLOW}Installing NVIDIA GPU dependencies...${NC}"
                pip install -r Requirements/requirements.nvidia.txt
                ;;
            2)
                echo -e "${YELLOW}Installing AMD GPU dependencies...${NC}"
                pip install -r Requirements/requirements.amd.txt
                ;;
        esac
    fi
    
    # Create nushell activation script
    cat > activate.nu << 'EOF'
let virtual_env = ([$env.VIRTUAL_ENV, '.venv'] | path join)
let bin = ([$virtual_env, 'bin'] | path join)
let-env PATH = ($bin | append $env.PATH)
let-env VIRTUAL_ENV = $virtual_env
EOF
    
    echo -e "${GREEN}Environment setup complete.${NC}"
}

# Function to check for system dependencies
check_system_dependencies() {
    echo -e "${YELLOW}Checking system dependencies...${NC}"
    echo -e "${GREEN}No additional system dependencies are required for this implementation.${NC}"
}

# Function to setup the agent
setup_agent() {
    echo -e "${CYAN}${BOLD}Setting up Agent${NC}"
    
    cleanup
    mkdir -p Config/SystemPrompts Config/defaults
    mkdir -p Core Tools Output Clients Docs Scheduler Requirements
    
    create_requirement_files
    check_system_dependencies
    
    detect_gpu
    local gpu_type=$?
    
    local skip_venv=false
    if [ -d ".venv" ]; then
        echo -e "${YELLOW}Existing virtual environment detected.${NC}"
        if [[ -z "$VIRTUAL_ENV" ]]; then
            source .venv/bin/activate 2>/dev/null || { echo -e "${RED}Failed to activate existing virtual environment. Creating a new one.${NC}"; skip_venv=false; }
        fi
        echo -e "${GREEN}Using existing virtual environment.${NC}"
        read -p "Would you like to reuse it? (y/n): " reuse_venv
        if [[ $reuse_venv =~ ^[Yy]$ ]]; then
            skip_venv=true
        fi
    fi
    
    setup_environment $gpu_type $skip_venv
    
    if [ ! -f "Config/config.yaml" ]; then
        echo -e "${YELLOW}Creating default configuration...${NC}"
        mkdir -p Config/defaults
        cat > Config/defaults/default_config.yaml << 'EOF'
# Default Agent Configuration

paths:
  projects_dir: projects

llm:
  default_model: deepseek
  models:
    - anthropic
    - deepseek
  anthropic:
    temperature: 0.7
    max_tokens: 4000
  deepseek:
    temperature: 0.7
    max_tokens: 4000

agent:
  headless: false
  test_mode: false
  max_inactivity: 3600
  allow_internet: true

logging:
  level: INFO
  log_to_file: true
  log_file: Config/agent.log
  log_commands: true
EOF
        cp Config/defaults/default_config.yaml Config/config.yaml
        echo -e "${GREEN}Default configuration created.${NC}"
    fi
    
    echo -e "${GREEN}Setup complete!${NC}"
    echo -e "${YELLOW}For bash, use: ${NC}source .venv/bin/activate"
    echo -e "${YELLOW}For nushell, use: ${NC}source activate.nu"
    echo -e "${YELLOW}To run all tests, use: ${NC}python test.py"
}

# Function to restore the agent to a clean state
restore_agent() {
    echo -e "${CYAN}${BOLD}Restoring Agent to clean state${NC}"
    echo -e "${RED}WARNING: This will delete all local changes and reset to the remote repository state.${NC}"
    read -p "Are you sure you want to continue? (y/n): " confirm
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Restore operation cancelled.${NC}"
        return
    fi
    
    echo -e "${YELLOW}Creating backup of current state...${NC}"
    local backup_time=$(date +%Y%m%d_%H%M%S)
    local backup_dir="agent_backup_$backup_time"
    mkdir -p "$backup_dir"
    
    if [ -f "Config/config.yaml" ]; then
        mkdir -p "$backup_dir/Config"
        cp -r Config "$backup_dir/"
        echo -e "${GREEN}Configuration backed up at $backup_dir/Config${NC}"
    fi
    
    if [ -f ".env" ]; then
        cp .env "$backup_dir/"
        echo -e "${GREEN}Environment file backed up at $backup_dir/.env${NC}"
    fi
    
    has_venv=false
    if [ -d ".venv" ]; then
        has_venv=true
        echo -e "${YELLOW}Existing virtual environment detected; it will be preserved.${NC}"
    fi
    
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    echo -e "${YELLOW}Fetching latest updates from remote...${NC}"
    git fetch origin
    
    if [ -f ".env" ]; then
        cp .env .env.tmp
    fi
    if [ -d "Config" ]; then
        mkdir -p Config.tmp
        cp -r Config/* Config.tmp/ 2>/dev/null || true
    fi
    
    echo -e "${YELLOW}Removing all untracked files and directories...${NC}"
    git clean -xdf --exclude=.venv --exclude=.env.tmp --exclude=Config.tmp
    echo -e "${YELLOW}Resetting all local changes...${NC}"
    git reset --hard origin/$current_branch
    
    if [ -f ".env.tmp" ]; then
        mv .env.tmp .env
        echo -e "${GREEN}.env file restored${NC}"
    fi
    if [ -d "Config.tmp" ] && [ -n "$(ls -A Config.tmp 2>/dev/null)" ]; then
        mkdir -p Config
        cp -r Config.tmp/* Config/ 2>/dev/null || true
        rm -rf Config.tmp
        echo -e "${GREEN}Configuration restored${NC}"
    fi
    
    echo -e "${YELLOW}Running setup process...${NC}"
    mkdir -p Config/SystemPrompts Config/defaults
    cleanup
    create_requirement_files
    detect_gpu
    local gpu_type=$?
    
    if [ "$has_venv" = true ]; then
        setup_environment $gpu_type true
    else
        setup_environment $gpu_type false
    fi
    
    echo -e "${GREEN}Complete restoration and setup finished!${NC}"
    echo -e "${GREEN}The Agent has been reset to the remote repository state and reinitialized.${NC}"
    echo -e "${YELLOW}A backup of your previous state was saved to $backup_dir${NC}"
}

# Function to update the agent from git
update_agent() {
    echo -e "${CYAN}${BOLD}Updating Agent from Git${NC}"
    
    if [ ! -d ".git" ]; then
        echo -e "${RED}This doesn't appear to be a git repository.${NC}"
        return
    fi
    
    if ! git diff-index --quiet HEAD --; then
        echo -e "${RED}You have uncommitted changes. Please commit or stash them before updating.${NC}"
        git status
        read -p "Would you like to stash your changes and continue? (y/n): " stash_changes
        if [[ $stash_changes =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}Stashing changes...${NC}"
            git stash save "Auto-stashed during update $(date)"
        else
            echo -e "${YELLOW}Update cancelled.${NC}"
            return
        fi
    fi
    
    echo -e "${YELLOW}Fetching latest updates...${NC}"
    git fetch
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    behind_count=$(git rev-list --count HEAD..origin/$current_branch)
    
    if [ "$behind_count" -eq "0" ]; then
        echo -e "${GREEN}You're already up to date.${NC}"
        return
    fi
    
    echo -e "${YELLOW}Your branch is behind by $behind_count commits.${NC}"
    echo -e "${YELLOW}Changes to be pulled:${NC}"
    git log --oneline --no-merges HEAD..origin/$current_branch
    read -p "Do you want to pull these changes? (y/n): " confirm_pull
    if [[ ! $confirm_pull =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Update cancelled.${NC}"
        return
    fi
    
    echo -e "${YELLOW}Pulling updates...${NC}"
    if git pull; then
        echo -e "${GREEN}Update successful!${NC}"
        echo -e "${YELLOW}Checking for dependency changes...${NC}"
        if git diff HEAD@{1} HEAD -- Requirements/requirements.txt | grep -q "^[+-]"; then
            echo -e "${YELLOW}Dependencies have changed. Updating virtual environment...${NC}"
            check_system_dependencies
            detect_gpu
            local gpu_type=$?
            create_requirement_files
            setup_environment $gpu_type true
        fi
    else
        echo -e "${RED}Update failed. Please check the error messages above.${NC}"
    fi
}

# Main menu
show_menu() {
    echo
    echo -e "${BLUE}${BOLD}Arcadia Agent Management Tool${NC}"
    echo "========================================"
    echo -e "${BOLD}Choose an operation:${NC}"
    echo "1) Setup Agent (Initialize or reconfigure)"
    echo "2) Restore Agent (Reset to clean state)"
    echo "3) Update Agent (Pull latest version from Git)"
    echo "q) Quit"
    echo
    read -p "Enter your choice: " choice
    
    case $choice in
        1)
            setup_agent
            ;;
        2)
            restore_agent
            ;;
        3)
            update_agent
            ;;
        q|Q)
            echo -e "${GREEN}Exiting.${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid choice.${NC}"
            ;;
    esac
    
    if [[ $choice =~ ^[123]$ ]]; then
        echo
        read -p "Press Enter to return to the main menu..."
        show_menu
    fi
}

# Run the menu
show_menu
