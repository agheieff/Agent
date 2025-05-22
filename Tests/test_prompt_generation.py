#!/usr/bin/env python3
"""
A small test script that generates and outputs the full system prompt.
Place this file in the project root and run it.
"""

from Prompts.main import generate_system_prompt

def main():
    # Set the provider for which you want to generate the system prompt.
    provider = "anthropic"
    prompt = generate_system_prompt(provider)
    print(prompt)

if __name__ == "__main__":
    main()
