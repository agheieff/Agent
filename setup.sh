#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
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
echo -e "${GREEN}Installing dependencies from requirements.txt...${NC}"
pip install -r requirements.txt

# Also install test requirements if they exist
if [ -f "Requirements/requirements.txt" ]; then
    echo -e "${GREEN}Installing test dependencies from Requirements/requirements.txt...${NC}"
    pip install -r Requirements/requirements.txt
fi

# Update pip
echo -e "${GREEN}Updating pip to latest version...${NC}"
pip install --upgrade pip

# Check for .env file and inform user
if [ -f ".env" ]; then
    echo -e "${GREEN}Found .env file with API keys.${NC}"
else
    echo -e "${RED}Warning: .env file not found. API keys will need to be set manually.${NC}"
    echo -e "${YELLOW}Create a .env file with the following variables:${NC}"
    echo -e "OPENAI_API_KEY=your_key_here"
    echo -e "ANTHROPIC_API_KEY=your_key_here"
    echo -e "DEEPSEEK_API_KEY=your_key_here (optional)"
    echo -e "GOOGLE_API_KEY=your_key_here (optional for Gemini)"
fi

# Make run.py executable
if [ -f "run.py" ]; then
    echo -e "${GREEN}Making run.py executable...${NC}"
    chmod +x run.py
fi

# Setup complete
echo -e "${YELLOW}Setup complete! Virtual environment is active.${NC}"
echo -e "${YELLOW}To activate the virtual environment in the future, run:${NC}"
echo -e "    source .venv/bin/activate"
echo -e "${YELLOW}To run the agent, use:${NC}"
echo -e "    ./run.py                                # Interactive provider/model selection"
echo -e "    ./run.py --provider anthropic           # Select model interactively"
echo -e "    ./run.py --provider openai --model gpt-4 # Specify both provider and model" 