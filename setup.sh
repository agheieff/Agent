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
    
    # Create CPU requirements - this is the default
    cp Requirements/requirements.txt Requirements/requirements.cpu.txt
    
    # Create NVIDIA GPU requirements
    cp Requirements/requirements.txt Requirements/requirements.nvidia.txt
    # Replace CPU-specific packages with GPU versions
    sed -i 's/faiss-cpu==1.10.0/faiss-gpu==1.10.0/g' Requirements/requirements.nvidia.txt
    # Add CUDA-specific packages if needed
    
    # Create AMD GPU requirements
    cp Requirements/requirements.txt Requirements/requirements.amd.txt
    # Replace CPU-specific packages with AMD versions
    sed -i 's/faiss-cpu==1.10.0/faiss-cpu==1.10.0/g' Requirements/requirements.amd.txt
    # Add ROCm-specific packages if needed
}

# Clean up unnecessary files and folders
cleanup() {
    echo -e "${YELLOW}Cleaning up project structure...${NC}"
    
    # Remove old virtual environments
    rm -rf new_venv .venv_snapshot_* 2>/dev/null || true
    
    # Remove temporary files
    find . -name "*.tmp" -type f -delete
    
    # Clean up old directories (with confirmation)
    if [ -d "memory" ] || [ -d "config" ] || [ -d "scheduler" ] || [ -f "memory.config" ] || [ -f "projects.config" ]; then
        echo -e "${YELLOW}Legacy directories and files detected.${NC}"
        read -p "Would you like to remove old lowercase directories (memory, config, scheduler) and config files? (y/n): " clean_legacy
        if [[ $clean_legacy =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}Removing legacy directories and files...${NC}"
            [ -d "memory" ] && rm -rf memory
            [ -d "config" ] && rm -rf config
            [ -d "scheduler" ] && rm -rf scheduler
            [ -f "memory.config" ] && rm -f memory.config
            [ -f "projects.config" ] && rm -f projects.config
            echo -e "${GREEN}Legacy directories and files removed.${NC}"
        fi
    fi
    
    # Ensure uppercase directory structure
    mkdir -p Config Core Memory Tools Output Clients Docs Scheduler Requirements
    
    echo -e "${GREEN}Cleanup complete.${NC}"
}

# Setup virtual environment and install dependencies
setup_environment() {
    local gpu_type=$1
    local skip_venv=$2
    
    echo -e "${YELLOW}Setting up virtual environment...${NC}"
    
    # Only remove existing .venv if skip_venv is false
    if [ "$skip_venv" = false ] && [ -d ".venv" ]; then
        echo -e "${YELLOW}Removing existing virtual environment...${NC}"
        rm -rf .venv
        
        # Create new virtual environment
        python -m venv .venv
        
        # Upgrade pip
        source .venv/bin/activate
        pip install --upgrade pip
        
        # Install dependencies based on hardware
        case $gpu_type in
            0) # CPU
                echo -e "${YELLOW}Installing CPU dependencies...${NC}"
                pip install -r Requirements/requirements.cpu.txt
                ;;
            1) # NVIDIA
                echo -e "${YELLOW}Installing NVIDIA GPU dependencies...${NC}"
                pip install -r Requirements/requirements.nvidia.txt
                ;;
            2) # AMD
                echo -e "${YELLOW}Installing AMD GPU dependencies...${NC}"
                pip install -r Requirements/requirements.amd.txt
                ;;
        esac
    elif [ -d ".venv" ]; then
        echo -e "${GREEN}Using existing virtual environment.${NC}"
        source .venv/bin/activate
    else
        # Create new virtual environment
        python -m venv .venv
        
        # Upgrade pip
        source .venv/bin/activate
        pip install --upgrade pip
        
        # Install dependencies based on hardware
        case $gpu_type in
            0) # CPU
                echo -e "${YELLOW}Installing CPU dependencies...${NC}"
                pip install -r Requirements/requirements.cpu.txt
                ;;
            1) # NVIDIA
                echo -e "${YELLOW}Installing NVIDIA GPU dependencies...${NC}"
                pip install -r Requirements/requirements.nvidia.txt
                ;;
            2) # AMD
                echo -e "${YELLOW}Installing AMD GPU dependencies...${NC}"
                pip install -r Requirements/requirements.amd.txt
                ;;
        esac
    fi
    
    # Create nushell activation script
    cat > activate.nu << 'EOF'
let virtual_env = ([$env.VIRTUAL_ENV, '.venv'] | path join)
let bin = ([$virtual_env, 'bin'] | path join)

# This puts the venv binary directory at the front of PATH
let-env PATH = ($bin | append $env.PATH)

# This sets VIRTUAL_ENV environment variable
let-env VIRTUAL_ENV = $virtual_env
EOF
    
    echo -e "${GREEN}Environment setup complete.${NC}"
}

# Function to check for system dependencies
check_system_dependencies() {
    echo -e "${YELLOW}Checking system dependencies...${NC}"
    
    # Check for libxml2 and libxslt development packages
    if command -v apt-get &> /dev/null; then
        # Debian/Ubuntu
        if ! dpkg -l libxml2-dev libxslt-dev 2>/dev/null | grep -q "^ii"; then
            echo -e "${YELLOW}Missing required system dependencies for lxml.${NC}"
            echo -e "${YELLOW}The following packages are required: libxml2-dev libxslt-dev${NC}"
            read -p "Would you like to install them now? (y/n): " install_deps
            if [[ $install_deps =~ ^[Yy]$ ]]; then
                echo -e "${YELLOW}Installing dependencies...${NC}"
                sudo apt-get update && sudo apt-get install -y libxml2-dev libxslt-dev
            else
                echo -e "${RED}Warning: lxml installation may fail without these dependencies.${NC}"
                echo -e "${YELLOW}You can install them manually with: sudo apt-get install libxml2-dev libxslt-dev${NC}"
            fi
        fi
    elif command -v yum &> /dev/null; then
        # RedHat/CentOS/Fedora
        if ! rpm -q libxml2-devel libxslt-devel &>/dev/null; then
            echo -e "${YELLOW}Missing required system dependencies for lxml.${NC}"
            echo -e "${YELLOW}The following packages are required: libxml2-devel libxslt-devel${NC}"
            read -p "Would you like to install them now? (y/n): " install_deps
            if [[ $install_deps =~ ^[Yy]$ ]]; then
                echo -e "${YELLOW}Installing dependencies...${NC}"
                sudo yum install -y libxml2-devel libxslt-devel
            else
                echo -e "${RED}Warning: lxml installation may fail without these dependencies.${NC}"
                echo -e "${YELLOW}You can install them manually with: sudo yum install libxml2-devel libxslt-devel${NC}"
            fi
        fi
    elif command -v pacman &> /dev/null; then
        # Arch Linux
        if ! pacman -Q libxml2 libxslt &>/dev/null; then
            echo -e "${YELLOW}Missing required system dependencies for lxml.${NC}"
            echo -e "${YELLOW}The following packages are required: libxml2 libxslt${NC}"
            read -p "Would you like to install them now? (y/n): " install_deps
            if [[ $install_deps =~ ^[Yy]$ ]]; then
                echo -e "${YELLOW}Installing dependencies...${NC}"
                sudo pacman -S --noconfirm libxml2 libxslt
            else
                echo -e "${RED}Warning: lxml installation may fail without these dependencies.${NC}"
                echo -e "${YELLOW}You can install them manually with: sudo pacman -S libxml2 libxslt${NC}"
            fi
        fi
    elif command -v brew &> /dev/null; then
        # macOS with Homebrew
        if ! brew list libxml2 libxslt &>/dev/null; then
            echo -e "${YELLOW}Missing required system dependencies for lxml.${NC}"
            echo -e "${YELLOW}The following packages are required: libxml2 libxslt${NC}"
            read -p "Would you like to install them now? (y/n): " install_deps
            if [[ $install_deps =~ ^[Yy]$ ]]; then
                echo -e "${YELLOW}Installing dependencies...${NC}"
                brew install libxml2 libxslt
                # Export PKG_CONFIG_PATH on macOS to help find the libraries
                export PKG_CONFIG_PATH="$(brew --prefix libxml2)/lib/pkgconfig:$(brew --prefix libxslt)/lib/pkgconfig:$PKG_CONFIG_PATH"
            else
                echo -e "${RED}Warning: lxml installation may fail without these dependencies.${NC}"
                echo -e "${YELLOW}You can install them manually with: brew install libxml2 libxslt${NC}"
            fi
        fi
    else
        echo -e "${YELLOW}Unable to detect package manager. Please ensure libxml2 and libxslt development packages are installed manually.${NC}"
        echo -e "${YELLOW}These are required for the lxml package to build successfully.${NC}"
    fi
}

# Function to setup the agent
setup_agent() {
    echo -e "${CYAN}${BOLD}Setting up Agent${NC}"
    
    # Clean up first
    cleanup
    
    # Create standard directory structure
    echo -e "${YELLOW}Creating standard directory structure...${NC}"
    mkdir -p Config/SystemPrompts Config/defaults
    mkdir -p Core Memory Tools Output Clients Docs Scheduler Requirements
    
    # Create requirements files for different hardware
    create_requirement_files
    
    # Check for system dependencies
    check_system_dependencies
    
    # Detect hardware
    detect_gpu
    local gpu_type=$?
    
    # Ask if we should reuse the existing venv
    local skip_venv=false
    if [ -d ".venv" ]; then
        echo -e "${YELLOW}Existing virtual environment detected.${NC}"
        read -p "Would you like to reuse it? (y/n): " reuse_venv
        if [[ $reuse_venv =~ ^[Yy]$ ]]; then
            skip_venv=true
        fi
    fi
    
    # Setup environment based on detected hardware
    setup_environment $gpu_type $skip_venv
    
    # Ensure config files exist
    if [ ! -f "Config/config.yaml" ]; then
        echo -e "${YELLOW}Creating default configuration...${NC}"
        mkdir -p Config/defaults
        
        # Create default config file
        cat > Config/defaults/default_config.yaml << 'EOF'
# Default Agent Configuration

# Base paths for agent operation
paths:
  # Memory storage location - where all agent memory will be stored
  memory_dir: memory
  
  # Projects directory - where code projects will be managed
  projects_dir: projects
  
  # Temporary file storage
  temp_dir: ${paths.memory_dir}/temp
  
  # Backup directory for agent memory
  backup_dir: ${paths.memory_dir}/backups

# Memory system configuration
memory:
  # Maximum size for indexed documents in bytes (1MB)
  max_document_size: 1048576
  
  # Maximum number of entries in vector index
  max_indexed_entries: 10000
  
  # Maximum number of backups to keep
  max_backups: 5
  
  # Backup interval in seconds (1 hour)
  backup_interval: 3600
  
  # Context keys to track
  context_keys:
    - system_config
    - tool_usage
    - error_history
    - active_projects
    - agent_notes
    - status_updates
    - command_skills
    - knowledge_base
    - important
    - task
    - mind_map
    - code
    - project

# LLM model configuration
llm:
  # Default model to use
  default_model: deepseek
  
  # Available models
  models:
    - anthropic
    - deepseek
  
  # Model-specific settings
  anthropic:
    temperature: 0.7
    max_tokens: 4000
  
  deepseek:
    temperature: 0.7
    max_tokens: 4000

# Agent behavior configuration
agent:
  # Whether to run in headless mode (no interactive prompts)
  headless: false
  
  # Whether to run in test mode (no actual commands executed)
  test_mode: false
  
  # Maximum inactivity time in seconds before agent auto-terminates (1 hour)
  max_inactivity: 3600
  
  # Whether to allow internet access
  allow_internet: true

# Security settings
security:
  # Maximum file size the agent can create/modify (100MB)
  max_file_size: 104857600

# Logging configuration
logging:
  # Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  level: INFO
  
  # Whether to log to file
  log_to_file: true
  
  # Log file path
  log_file: ${paths.memory_dir}/logs/agent.log
  
  # Whether to log command executions
  log_commands: true
EOF

        # Copy default config to main config
        cp Config/defaults/default_config.yaml Config/config.yaml
        echo -e "${GREEN}Default configuration created.${NC}"
    fi
    
    # Create required directories
    echo -e "${YELLOW}Creating required directories...${NC}"
    mkdir -p Memory/Data Memory/Graph Memory/Hierarchy Memory/Manager Memory/Temporal Memory/Text Memory/Vector
    
    echo -e "${GREEN}Setup complete!${NC}"
    echo -e "${YELLOW}For bash, use: ${NC}source .venv/bin/activate"
    echo -e "${YELLOW}For nushell, use: ${NC}source activate.nu"
}

# Function to restore the agent to a clean state
restore_agent() {
    echo -e "${CYAN}${BOLD}Restoring Agent to clean state${NC}"
    echo -e "${RED}WARNING: This will delete all local changes, reset to the remote repository state, and reinitialize the agent.${NC}"
    echo -e "${RED}Only your .venv directory and .env file will be preserved.${NC}"
    read -p "Are you sure you want to continue? (y/n): " confirm
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Restore operation cancelled.${NC}"
        return
    fi
    
    echo -e "${YELLOW}Creating backup of current state...${NC}"
    local backup_time=$(date +%Y%m%d_%H%M%S)
    local backup_dir="agent_backup_$backup_time"
    mkdir -p "$backup_dir"
    
    # Save current config if it exists
    if [ -f "Config/config.yaml" ]; then
        mkdir -p "$backup_dir/Config"
        cp -r Config "$backup_dir/"
        echo -e "${GREEN}Configuration backed up at $backup_dir/Config${NC}"
    fi
    
    # Backup memory directory if it exists (both lowercase and uppercase)
    if [ -d "Memory" ]; then
        cp -r Memory "$backup_dir/"
        echo -e "${GREEN}Memory backup created at $backup_dir/Memory${NC}"
    fi
    if [ -d "memory" ]; then
        cp -r memory "$backup_dir/memory_old"
        echo -e "${GREEN}Old memory backup created at $backup_dir/memory_old${NC}"
    fi
    
    # Backup .env file if it exists
    if [ -f ".env" ]; then
        cp .env "$backup_dir/"
        echo -e "${GREEN}Environment file backed up at $backup_dir/.env${NC}"
    fi
    
    # Determine if .venv exists to restore it later
    has_venv=false
    if [ -d ".venv" ]; then
        has_venv=true
        echo -e "${YELLOW}Detected existing virtual environment, it will be preserved.${NC}"
    fi
    
    # Get the name of the current branch
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    
    # Fetch latest from remote
    echo -e "${YELLOW}Fetching latest updates from remote...${NC}"
    git fetch origin
    
    # Stash .env and Config if they exist (to prevent them from being removed)
    if [ -f ".env" ]; then
        cp .env .env.tmp
    fi
    if [ -d "Config" ]; then
        mkdir -p Config.tmp
        cp -r Config/* Config.tmp/ 2>/dev/null || true
    fi
    
    # Clean all untracked files and directories
    echo -e "${YELLOW}Removing all untracked files and directories...${NC}"
    git clean -xdf --exclude=.venv --exclude=.env.tmp --exclude=Config.tmp
    
    # Reset all changes to tracked files
    echo -e "${YELLOW}Resetting all local changes...${NC}"
    git reset --hard origin/$current_branch
    
    # Restore .env file and Config directory
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
    
    # Run setup process automatically
    echo -e "${YELLOW}Running setup process...${NC}"
    
    # Create standard directory structure
    echo -e "${YELLOW}Creating standard directory structure...${NC}"
    mkdir -p Config/SystemPrompts Config/defaults
    mkdir -p Core Memory Tools Output Clients Docs Scheduler Requirements
    
    # Clean up first
    cleanup
    
    # Create requirements files for different hardware
    create_requirement_files
    
    # Detect hardware
    detect_gpu
    local gpu_type=$?
    
    # Setup environment using existing venv if available
    if [ "$has_venv" = true ]; then
        setup_environment $gpu_type true
    else
        setup_environment $gpu_type false
    fi
    
    # Create required memory structure
    echo -e "${YELLOW}Creating memory directories...${NC}"
    mkdir -p Memory/Data Memory/Graph Memory/Hierarchy Memory/Manager Memory/Temporal Memory/Text Memory/Vector
    
    echo -e "${GREEN}Complete restoration and setup finished!${NC}"
    echo -e "${GREEN}The Agent has been reset to the remote repository state and reinitialized.${NC}"
    echo -e "${YELLOW}A backup of your previous state was saved to $backup_dir${NC}"
}

# Function to update the agent from git
update_agent() {
    echo -e "${CYAN}${BOLD}Updating Agent from Git${NC}"
    
    # Check if this is a git repository
    if [ ! -d ".git" ]; then
        echo -e "${RED}This doesn't appear to be a git repository.${NC}"
        return
    fi
    
    # Check for uncommitted changes
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
    
    # Get current branch
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    
    # Count how many commits we're behind
    behind_count=$(git rev-list --count HEAD..origin/$current_branch)
    
    if [ "$behind_count" -eq "0" ]; then
        echo -e "${GREEN}You're already up to date.${NC}"
        return
    fi
    
    echo -e "${YELLOW}Your branch is behind by $behind_count commits.${NC}"
    
    # Show what changes will be pulled
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
        
        # Check if requirements have changed
        echo -e "${YELLOW}Checking for dependency changes...${NC}"
        if git diff HEAD@{1} HEAD -- Requirements/requirements.txt | grep -q "^[+-]"; then
            echo -e "${YELLOW}Dependencies have changed. Updating virtual environment...${NC}"
            
            # Check for system dependencies first
            check_system_dependencies
            
            # Detect hardware
            detect_gpu
            local gpu_type=$?
            
            # Update requirement files
            create_requirement_files
            
            # Setup environment without recreating venv
            setup_environment $gpu_type true
        fi
        
        # Run any post-update steps if needed
        echo -e "${YELLOW}Running post-update steps...${NC}"
        # Example: migrations or data structure updates would go here
        # For now, we just make sure all directories exist
        mkdir -p Memory/Data Memory/Graph Memory/Hierarchy Memory/Manager Memory/Temporal Memory/Text Memory/Vector
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
    
    # Return to menu after operation completes
    if [[ $choice =~ ^[123]$ ]]; then
        echo
        read -p "Press Enter to return to the main menu..."
        show_menu
    fi
}

# Run the menu
show_menu