#!/usr/bin/env python3
"""
Generates and prints the system prompt based on discovered MCP Operations.
Run this script from the project root directory: python prompt_test.py
"""
import os
import sys
import logging

# Ensure project root is in path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Configure basic logging for prompt generation module if needed
logging.basicConfig(level=logging.INFO)

try:
    from Prompts.main import generate_system_prompt
except ImportError as e:
    print(f"Error: Could not import prompt generation components. "
          f"Make sure you run this from the project root and all dependencies are installed. Details: {e}")
    sys.exit(1)


def main():
    """Generates and prints the system prompt."""
    # Example: Generate prompt for Anthropic provider
    provider = "anthropic"
    print(f"--- Generating System Prompt (Provider: {provider or 'Generic'}) ---")
    try:
        prompt = generate_system_prompt(provider=provider)
        print(prompt)
    except Exception as e:
        print(f"\nError during prompt generation: {e}")
        logging.exception("Prompt generation failed.") # Log traceback
    finally:
        print("\n--- End Prompt ---")

if __name__ == "__main__":
    main()
