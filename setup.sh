#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Setting up Agent development environment...${NC}"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo -e "${GREEN}Creating virtual environment in .venv/...${NC}"
    python3 -m venv .venv
else
    echo -e "${GREEN}Virtual environment already exists in .venv/...${NC}"
fi

# Activate virtual environment
echo -e "${GREEN}Activating virtual environment...${NC}"
source .venv/bin/activate

# Install requirements
echo -e "${GREEN}Installing dependencies from Requirements/requirements.txt...${NC}"
pip install -r Requirements/requirements.txt

# Update pip
echo -e "${GREEN}Updating pip to latest version...${NC}"
pip install --upgrade pip

# Setup complete
echo -e "${YELLOW}Setup complete! Virtual environment is active.${NC}"
echo -e "${YELLOW}To activate the virtual environment in the future, run:${NC}"
echo -e "    source .venv/bin/activate" 