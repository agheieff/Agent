"""
Utility functions for the Agent application.
"""

def get_multiline_input(prompt: str = "> ") -> str:
    """
    Get multiline input from the user.
    
    Pressing Enter once adds a newline, while pressing Enter twice (creating an empty line) submits the input.
    
    Args:
        prompt: The prompt to display for the first line
        
    Returns:
        The complete multiline input
    """
    print(prompt, end="", flush=True)
    lines = []
    
    # For the first line, show the prompt
    line = input()
    lines.append(line)
    
    # For subsequent lines, use a continuation prompt
    continuation_prompt = "... "
    
    while True:
        # Show a continuation prompt
        print(continuation_prompt, end="", flush=True)
        line = input()
        
        # If the line is empty and we already have at least one line, submit the input
        if not line and lines:
            break
        
        # Otherwise, add the line and continue
        lines.append(line)
    
    # Join the lines with newlines
    return "\n".join(lines) 