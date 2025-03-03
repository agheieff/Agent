#\!/bin/bash
source .venv/bin/activate
echo "List files in the current directory" | python run_agent.py -v --provider deepseek --model deepseek-reasoner --test --headless
