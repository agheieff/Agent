"""
Parser for extracting tool calls from agent messages.
"""

import re
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class ToolParser:
    @staticmethod
    def extract_tool_calls(message: str) -> List[Tuple[str, Dict[str, Any], bool]]:
        tool_calls = []

        tool_pattern = r'/(\w+)(?:\s+(.*?))?(?:\s*$|\n)'
        matches = re.finditer(tool_pattern, message, re.MULTILINE | re.DOTALL)
        for match in matches:
            tool_name = match.group(1)
            args_text = match.group(2) if match.group(2) else ""
            if args_text.strip() == "-h" or args_text.strip() == "--help":
                tool_calls.append((tool_name, {}, True))
                continue
            params = {}
            heredoc_pattern = r'(\w+)=("""|\'\'\')(.*?)\2'
            processed_args = args_text
            heredoc_matches = list(re.finditer(heredoc_pattern, args_text, re.DOTALL))
            for h_match in heredoc_matches:
                param_name = h_match.group(1)
                param_value = h_match.group(3)
                params[param_name] = param_value
                start, end = h_match.span()
                processed_args = processed_args[:start] + f"{param_name}=HEREDOC_PLACEHOLDER" + processed_args[end:]
            placeholder_map = {}
            placeholder_pattern = "__PLACEHOLDER_{}__"
            placeholder_counter = 0
            def replace_quoted(match):
                nonlocal placeholder_counter
                placeholder = placeholder_pattern.format(placeholder_counter)
                placeholder_counter += 1
                placeholder_map[placeholder] = match.group(1) or match.group(2)
                return f" {placeholder} "
            processed_args = re.sub(r'(["\'])(.*?)\1', replace_quoted, processed_args)
            param_pattern = r'(\w+)=(\S+)'
            param_matches = re.finditer(param_pattern, processed_args)
            positional_values = []
            named_params_found = False
            for param_match in param_matches:
                param_name = param_match.group(1)
                if param_name in params and param_match.group(2) == "HEREDOC_PLACEHOLDER":
                    continue
                named_params_found = True
                key = param_name
                value = param_match.group(2)
                if value in placeholder_map:
                    value = placeholder_map[value]
                params[key] = value
                processed_args = processed_args.replace(param_match.group(0), "", 1)
            remaining_args = processed_args.strip().split()
            for i, arg in enumerate(remaining_args):
                if arg in placeholder_map:
                    positional_values.append(placeholder_map[arg])
                else:
                    positional_values.append(arg)
            if positional_values:
                if named_params_found:
                    for i, value in enumerate(positional_values):
                        params[str(i)] = value
                else:
                    if len(positional_values) == 1:
                        params["value"] = positional_values[0]
                    else:
                        for i, value in enumerate(positional_values):
                            params[str(i)] = value
            tool_calls.append((tool_name, params, False))
        return tool_calls
