def parse_tool_call(self, text: str) -> Dict[str, Any]:
    """
    Parses tool call with explicit multi-line delimiters.
    Handles:
    - Single-line arguments (arg: value)
    - Multi-line arguments (arg: <<< ... >>>)
    - Mixed argument types
    """
    pattern = r'@tool\s+(?P<name>\w+)\s+(?P<args>.*?)@end'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        raise ValueError("Invalid tool call format")
    
    args = {}
    current_arg = None
    in_multiline = False
    multiline_content = []
    
    for line in match.group('args').strip().split('\n'):
        if in_multiline:
            if line.strip() == '>>>':
                args[current_arg] = '\n'.join(multiline_content)
                in_multiline = False
                multiline_content = []
            else:
                multiline_content.append(line)
        elif ':' in line:
            arg_part, value_part = line.split(':', 1)
            arg = arg_part.strip()
            value = value_part.strip()
            
            if value.startswith('<<<'):
                current_arg = arg
                in_multiline = True
            else:
                args[arg] = value
    
    return {
        'tool': match.group('name'),
        'args': args
    }
