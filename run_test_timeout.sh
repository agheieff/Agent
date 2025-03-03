#\!/bin/bash
source .venv/bin/activate
timeout 20s python run_agent.py -v --provider deepseek --model deepseek-reasoner --test --headless <<< "List files in the current directory"
