#!/bin/bash

set -e  # Exit immediately if a command exits with a non-zero status

# Colors for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Arcadia Agent Setup${NC}"
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
    
    echo -e "${YELLOW}Setting up virtual environment...${NC}"
    
    # Remove existing .venv if it exists
    if [ -d ".venv" ]; then
        echo -e "${YELLOW}Removing existing virtual environment...${NC}"
        rm -rf .venv
    fi
    
    # Create new virtual environment
    python -m venv .venv
    
    # Activate virtual environment
    source .venv/bin/activate
    
    # Upgrade pip
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

# Main function
main() {
    # Clean up first
    cleanup
    
    # Create requirements files for different hardware
    create_requirement_files
    
    # Detect hardware
    detect_gpu
    local gpu_type=$?
    
    # Setup environment based on detected hardware
    setup_environment $gpu_type
    
    echo -e "${GREEN}Setup complete!${NC}"
    echo -e "${YELLOW}For bash, use: ${NC}source .venv/bin/activate"
    echo -e "${YELLOW}For nushell, use: ${NC}source activate.nu"
}

# Run the main function
main