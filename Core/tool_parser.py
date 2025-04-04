class ToolCallParser:
    def __init__(self):
        self.buffer = ""
        self.in_tool = False
        self.tool_depth = 0
        self.tool_pattern = re.compile(r'@tool\s+(\w+)')

    def feed(self, text: str) -> Tuple[str, Optional[Dict]]:
        self.buffer += text
        output = []
        tool_call = None

        i = 0
        while i < len(self.buffer):
            if not self.in_tool:
                # Look for start of tool call
                if self.buffer.startswith('@tool', i):
                    self.in_tool = True
                    self.tool_depth = 1
                    tool_start = i
                    i += 5  # skip '@tool'
                    continue
                output.append(self.buffer[i])
                i += 1
            else:
                # Inside tool call
                if self.buffer.startswith('@end', i):
                    self.tool_depth -= 1
                    if self.tool_depth == 0:
                        tool_text = self.buffer[tool_start:i+4]
                        try:
                            tool_call = parse_tool_call(tool_text)
                        except ValueError:
                            # Invalid tool call, treat as text
                            output.append(tool_text)
                        self.in_tool = False
                        i += 4  # skip '@end'
                        continue
                    else:
                        i += 4
                elif self.buffer.startswith('@tool', i):
                    self.tool_depth += 1
                    i += 5
                else:
                    i += 1

        self.buffer = self.buffer[i:] if self.in_tool else ""
        return ''.join(output), tool_call
