def get_multiline_input(prompt: str = "> ") -> str:
    print(prompt, end="", flush=True)
    lines = []
    line = input()
    lines.append(line)
    continuation_prompt = "... "
    while True:
        print(continuation_prompt, end="", flush=True)
        line = input()
        if not line and lines:
            break
        lines.append(line)
    return "\n".join(lines) 
