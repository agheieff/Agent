class ToolCallParser:
    def __init__(self):
        self.buffer = ""
        self.state = "TEXT"  # TEXT, TOOL_START, TOOL_BODY, TOOL_END
        self.tool_depth = 0
        self.current_tool = ""
        self.pending_text = ""

    def feed(self, text: str) -> Tuple[str, Optional[Dict]]:
        self.buffer += text
        output = []
        tool_call = None

        while self.buffer:
            if self.state == "TEXT":
                tool_start = self.buffer.find("@tool")
                if tool_start >= 0:
                    output.append(self.buffer[:tool_start])
                    self.buffer = self.buffer[tool_start:]
                    self.state = "TOOL_START"
                else:
                    output.append(self.buffer)
                    self.buffer = ""

            elif self.state == "TOOL_START":
                if len(self.buffer) >= 5 and self.buffer.startswith("@tool"):
                    self.buffer = self.buffer[5:].lstrip()
                    self.state = "TOOL_BODY"
                    self.tool_depth = 1
                    self.current_tool = ""
                else:
                    output.append("@tool" + self.buffer)
                    self.buffer = ""
                    self.state = "TEXT"

            elif self.state == "TOOL_BODY":
                end_pos = self.buffer.find("@end")
                tool_pos = self.buffer.find("@tool")

                if end_pos >= 0 and (tool_pos < 0 or end_pos < tool_pos):
                    self.current_tool += self.buffer[:end_pos]
                    self.buffer = self.buffer[end_pos:]
                    self.state = "TOOL_END"
                elif tool_pos >= 0:
                    self.current_tool += self.buffer[:tool_pos]
                    self.buffer = self.buffer[tool_pos:]
                    self.tool_depth += 1
                    self.state = "TOOL_START"
                else:
                    self.current_tool += self.buffer
                    self.buffer = ""

            elif self.state == "TOOL_END":
                if len(self.buffer) >= 4 and self.buffer.startswith("@end"):
                    self.tool_depth -= 1
                    if self.tool_depth == 0:
                        try:
                            tool_call = parse_tool_call("@tool" + self.current_tool + "@end")
                            self.state = "TEXT"
                            self.current_tool = ""
                            self.buffer = self.buffer[4:]
                            break
                        except ValueError:
                            output.append("@tool" + self.current_tool + "@end")
                            self.state = "TEXT"
                            self.current_tool = ""
                            self.buffer = self.buffer[4:]
                    else:
                        self.current_tool += "@end"
                        self.buffer = self.buffer[4:]
                        self.state = "TOOL_BODY"
                else:
                    self.current_tool += self.buffer
                    self.buffer = ""

        return ''.join(output), tool_call
