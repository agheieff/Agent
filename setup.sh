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
    # Create CPU requirements - this is the default
    cp requirements.txt requirements.cpu.txt
    
    # Create NVIDIA GPU requirements
    cp requirements.txt requirements.nvidia.txt
    # Replace CPU-specific packages with GPU versions
    sed -i 's/faiss-cpu==1.10.0/faiss-gpu==1.10.0/g' requirements.nvidia.txt
    # Add CUDA-specific packages if needed
    
    # Create AMD GPU requirements
    cp requirements.txt requirements.amd.txt
    # Replace CPU-specific packages with AMD versions
    sed -i 's/faiss-cpu==1.10.0/faiss-cpu==1.10.0/g' requirements.amd.txt
    # Add ROCm-specific packages if needed
}

# Clean up unnecessary files and folders
cleanup() {
    echo -e "${YELLOW}Cleaning up project structure...${NC}"
    
    # Remove old virtual environments
    rm -rf new_venv .venv_snapshot_* 2>/dev/null || true
    
    # Remove temporary files
    find . -name "*.tmp" -type f -delete
    
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
                pip install -r requirements.cpu.txt
                ;;
            1) # NVIDIA
                echo -e "${YELLOW}Installing NVIDIA GPU dependencies...${NC}"
                pip install -r requirements.nvidia.txt
                ;;
            2) # AMD
                echo -e "${YELLOW}Installing AMD GPU dependencies...${NC}"
                pip install -r requirements.amd.txt
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
                pip install -r requirements.cpu.txt
                ;;
            1) # NVIDIA
                echo -e "${YELLOW}Installing NVIDIA GPU dependencies...${NC}"
                pip install -r requirements.nvidia.txt
                ;;
            2) # AMD
                echo -e "${YELLOW}Installing AMD GPU dependencies...${NC}"
                pip install -r requirements.amd.txt
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

# Function to setup the agent
setup_agent() {
    echo -e "${CYAN}${BOLD}Setting up Arcadia Agent${NC}"
    
    # Clean up first
    cleanup
    
    # Create requirements files for different hardware
    create_requirement_files
    
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
    
    # Create required directories
    echo -e "${YELLOW}Creating required directories...${NC}"
    mkdir -p memory/conversations memory/logs memory/summaries memory/config memory/scripts
    mkdir -p memory/data memory/temp memory/state memory/sessions memory/reflections
    mkdir -p memory/working_memory memory/tasks memory/plans memory/archive memory/notes
    mkdir -p memory/vector_index memory/knowledge/docs memory/documents
    
    echo -e "${GREEN}Setup complete!${NC}"
    echo -e "${YELLOW}For bash, use: ${NC}source .venv/bin/activate"
    echo -e "${YELLOW}For nushell, use: ${NC}source activate.nu"
}

# Function to restore the agent to a clean state
restore_agent() {
    echo -e "${CYAN}${BOLD}Restoring Arcadia Agent to clean state${NC}"
    echo -e "${RED}WARNING: This will delete all memory data and reset the agent to its initial state.${NC}"
    read -p "Are you sure you want to continue? (y/n): " confirm
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Restore operation cancelled.${NC}"
        return
    fi
    
    echo -e "${YELLOW}Creating backup of current state...${NC}"
    local backup_time=$(date +%Y%m%d_%H%M%S)
    local backup_dir="agent_backup_$backup_time"
    mkdir -p "$backup_dir"
    
    # Backup memory directory if it exists
    if [ -d "memory" ]; then
        cp -r memory "$backup_dir/"
        echo -e "${GREEN}Memory backup created at $backup_dir/memory${NC}"
    fi
    
    # Get a list of files tracked by git
    echo -e "${YELLOW}Identifying files to preserve...${NC}"
    git_files=$(git ls-files)
    
    # Delete everything except git tracked files, .git directory, .venv, and .env file
    echo -e "${YELLOW}Cleaning up non-tracked files...${NC}"
    find . -type f -not -path "./.git/*" -not -path "./.venv/*" | while read file; do
        # Check if the file is tracked by git
        if ! echo "$git_files" | grep -q "^${file#./}$"; then
            # Keep .env file if it exists
            if [ "$file" != "./.env" ]; then
                rm "$file"
            fi
        fi
    done
    
    # Remove directories that aren't tracked by git except .git and .venv
    find . -type d -not -path "." -not -path "./.git" -not -path "./.git/*" -not -path "./.venv" -not -path "./.venv/*" | while read dir; do
        # Check if the directory contains any git tracked files
        if ! echo "$git_files" | grep -q "^${dir#./}/"; then
            rm -rf "$dir"
        fi
    done
    
    # Recreate minimal directory structure
    echo -e "${YELLOW}Creating minimal directory structure...${NC}"
    mkdir -p memory
    
    echo -e "${GREEN}Agent restored to clean state.${NC}"
    echo -e "${YELLOW}A backup of your previous state was saved to $backup_dir${NC}"
    echo -e "${YELLOW}Run the setup option to fully initialize the agent.${NC}"
}

# Function to update the agent from git
update_agent() {
    echo -e "${CYAN}${BOLD}Updating Arcadia Agent from Git${NC}"
    
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
        if git diff HEAD@{1} HEAD -- requirements.txt | grep -q "^[+-]"; then
            echo -e "${YELLOW}Dependencies have changed. Updating virtual environment...${NC}"
            
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
        mkdir -p memory/conversations memory/logs memory/summaries memory/config memory/scripts
        mkdir -p memory/data memory/temp memory/state memory/sessions memory/reflections
        mkdir -p memory/working_memory memory/tasks memory/plans memory/archive memory/notes
        mkdir -p memory/vector_index memory/knowledge/docs memory/documents
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