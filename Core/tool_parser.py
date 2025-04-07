from typing import Tuple, Optional, Dict, Any
from Core.executor import parse_tool_call # Assuming parse_tool_call is still needed
import re

class ToolCallParser:
    def __init__(self):
        self.buffer = ""
        self.parsing_tool = False # State flag to know if we are inside @tool ...

    def feed(self, text: str) -> Tuple[str, Optional[Dict]]:
        """
        Processes an incoming text chunk, returns displayable text and completed tool data.

        Args:
            text: The incoming text chunk from the stream.

        Returns:
            A tuple containing:
            - str: Text that should be displayed/accumulated from this chunk.
            - Optional[Dict]: A dictionary representing a completed tool call, or None.
        """
        output_text = ""
        tool_data = None

        # If not currently inside a tool block, check if this chunk starts one
        if not self.parsing_tool:
            # Can we find the start tag *anywhere* in the combined buffer + new text?
            combined = self.buffer + text
            tool_start_index = combined.find("@tool")

            if tool_start_index != -1:
                # Tool starts! Output text *before* the tag from the combined buffer.
                output_text = combined[:tool_start_index]
                # Update buffer to contain only the start of the tool call onwards
                self.buffer = combined[tool_start_index:]
                self.parsing_tool = True
            else:
                # No tool start detected yet. The new text chunk is pure output.
                # Output the *new* text chunk immediately.
                output_text = text
                # Keep appending to buffer in case a tool call spans chunks.
                self.buffer += text
                # Optimization: If buffer gets very large without finding '@tool',
                # we might want to flush parts of it as output_text anyway.
                # For now, let's keep it simple. If buffer grows huge, add check later.

        # If we *are* (or just became) inside a tool block, add text and check for the end
        else: # self.parsing_tool is True
             self.buffer += text # Add new chunk to the tool buffer
             tool_end_index = self.buffer.find("@end")
             if tool_end_index != -1:
                 # Tool ends! Parse it.
                 tool_section = self.buffer[:tool_end_index + 4] # Include "@end"
                 self.buffer = self.buffer[tool_end_index + 4:] # Keep remaining buffer
                 self.parsing_tool = False # Reset state

                 try:
                     tool_data = parse_tool_call(tool_section)
                 except ValueError as e:
                     # Invalid tool format. What to do?
                     # Option 1: Treat as text -> potentially output gibberish
                     # Option 2: Log error and discard -> might lose agent intent
                     # Let's log and maybe return error text? For now, just log.
                     print(f"Warning: Invalid tool format detected and skipped: {e}")
                     # output_text = tool_section # Decide if you want to output bad tool calls

                 # If there was content in the buffer *after* the tool end,
                 # process it immediately in case it starts another tool etc.
                 # This requires a recursive call or a loop, let's simplify for now
                 # and assume the next feed() call will handle the remaining buffer.

        return output_text, tool_data
