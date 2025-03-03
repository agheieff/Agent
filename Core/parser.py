"""
Parser for extracting tool calls from agent messages.
"""

import re
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class ToolParser:
    """
    Parser that extracts tool calls from agent messages.
    Tool format: /tool_name [params]
    Help format: /tool_name -h
    
    Supports heredoc-style multiline parameters using triple quotes:
    /tool_name param="""multiline
    content"""
    """

    @staticmethod
    def extract_tool_calls(message: str) -> List[Tuple[str, Dict[str, Any], bool]]:
        """
        Extract tool calls from an agent message.

        Args:
            message: The message to parse

        Returns:
            List of tuples containing (tool_name, params_dict, is_help_request)
        """
        tool_calls = []

        # Pattern for tool call with parameters:
        # /tool_name param1=value1 param2="value with spaces" param3='another value'
        tool_pattern = r'/(\w+)(?:\s+((?:[^-]|\-[^h]|(?:\-h\S)).*?))?(?:\s*$|\n)'
        matches = re.finditer(tool_pattern, message, re.MULTILINE | re.DOTALL)

        for match in matches:
            tool_name = match.group(1)
            args_text = match.group(2) if match.group(2) else ""

            # Check if this is a help request
            if args_text.strip() == "-h" or args_text.strip() == "--help":
                tool_calls.append((tool_name, {}, True))
                continue

            # Parse the parameters
            params = {}

            # Handle heredoc-style multiline parameters with triple quotes
            # Look for param="""...""" or param='''...''' patterns
            heredoc_pattern = r'(\w+)=("""|\'\'\')(.*?)\2'
            
            # Process args_text to handle heredoc with placeholders
            processed_args = args_text
            heredoc_matches = list(re.finditer(heredoc_pattern, args_text, re.DOTALL))
            
            for h_match in heredoc_matches:
                param_name = h_match.group(1)
                param_value = h_match.group(3)
                params[param_name] = param_value
                
                # Replace the heredoc in args_text with a placeholder to avoid parsing issues
                start, end = h_match.span()
                processed_args = processed_args[:start] + f"{param_name}=HEREDOC_PLACEHOLDER" + processed_args[end:]

            # Handle quoted strings and preserve spaces within quotes
            placeholder_map = {}
            placeholder_pattern = "__PLACEHOLDER_{}__"
            placeholder_counter = 0

            # Replace quoted strings with placeholders to make parsing easier
            def replace_quoted(match):
                nonlocal placeholder_counter
                placeholder = placeholder_pattern.format(placeholder_counter)
                placeholder_counter += 1
                # Store the quoted value (without quotes) in the map
                placeholder_map[placeholder] = match.group(1) or match.group(2)
                return f" {placeholder} "

            # Replace quoted strings (that aren't already heredoc) with placeholders
            processed_args = re.sub(r'(["\'])(.*?)\1', replace_quoted, processed_args)

            # Process named parameters (key=value)
            param_pattern = r'(\w+)=(\S+)'
            param_matches = re.finditer(param_pattern, processed_args)

            positional_values = []
            named_params_found = False

            for param_match in param_matches:
                # Skip if we already processed this parameter as heredoc
                param_name = param_match.group(1)
                if param_name in params and param_match.group(2) == "HEREDOC_PLACEHOLDER":
                    continue
                    
                named_params_found = True
                key = param_name
                value = param_match.group(2)

                # Replace placeholder with original quoted value if present
                if value in placeholder_map:
                    value = placeholder_map[value]

                params[key] = value

                # Remove this parameter from processed_args so we can handle positional params
                processed_args = processed_args.replace(param_match.group(0), "", 1)

            # If any part of args_text wasn't consumed by named parameters, treat as positional
            remaining_args = processed_args.strip().split()

            # Process remaining positional parameters
            for i, arg in enumerate(remaining_args):
                if arg in placeholder_map:
                    positional_values.append(placeholder_map[arg])
                else:
                    positional_values.append(arg)

            # Add positional parameters to the params dictionary
            if positional_values:
                # Only use numeric keys for positional params if we also have named params
                # Otherwise, assume the first positional param is the primary argument
                if named_params_found:
                    for i, value in enumerate(positional_values):
                        params[str(i)] = value
                else:
                    # If no named params and just one positional value, use a more semantic key
                    if len(positional_values) == 1:
                        params["value"] = positional_values[0]
                    else:
                        # If multiple positional values, use numeric keys
                        for i, value in enumerate(positional_values):
                            params[str(i)] = value

            tool_calls.append((tool_name, params, False))

        return tool_calls
