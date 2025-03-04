import json
import logging
from typing import List, Dict, Any, Tuple, Optional, Type, Protocol, Union
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class FormatParser(ABC):


    @abstractmethod
    def parse(self, message: str) -> Dict[str, Any]:

        pass

    @abstractmethod
    def can_parse(self, message: str) -> bool:

        pass

class CLIFormatParser(FormatParser):


    def can_parse(self, message: str) -> bool:

        return any(line.strip().startswith('/') for line in message.strip().split('\n'))

    def parse(self, message: str) -> Dict[str, Any]:

        tool_calls = self.extract_tool_calls(message)

        if not tool_calls:
            return {
                "thinking": "",
                "analysis": "",
                "tool_calls": [],
                "answer": message
            }

        parsed_tool_calls = []
        for tool_name, params, is_help in tool_calls:
            parsed_tool_calls.append({
                "name": tool_name,
                "params": params,
                "help": is_help
            })

        return {
            "thinking": "",
            "analysis": "",
            "tool_calls": parsed_tool_calls,
            "answer": ""
        }

    def extract_tool_calls(self, message: str) -> List[Tuple[str, Dict[str, str], bool]]:

        result = []
        lines = message.strip().split('\n')

        for line in lines:
            if not line.strip().startswith('/'):
                continue

            parts = line.strip().split(' ')
            if len(parts) < 1:
                continue

            tool_name = parts[0][1:]
            is_help = False
            params = {}

            for i, part in enumerate(parts[1:], 1):
                if part in ['-h', '--help']:
                    is_help = True
                    continue

                if '=' in part:
                    key, value = part.split('=', 1)
                    params[key] = value
                elif i == 1 and not '=' in parts[1:]:
                    params['value'] = part

            result.append((tool_name, params, is_help))

        return result

class JSONFormatParser(FormatParser):


    def can_parse(self, message: str) -> bool:

        message = message.strip()
        return (message.startswith('{') and message.endswith('}')) or \
               (message.startswith('[') and message.endswith(']'))

    def parse(self, message: str) -> Dict[str, Any]:

        try:
            data = json.loads(message.strip())

            if not isinstance(data, dict):
                raise ValueError("Top-level JSON must be an object.")

            parsed = {
                "thinking": data.get("thinking", ""),
                "analysis": data.get("analysis", ""),
                "tool_calls": data.get("tool_calls", []),
                "answer": data.get("answer", "")
            }


            if not isinstance(parsed["tool_calls"], list):
                logger.warning("tool_calls is not a list; forcing it to be an empty list.")
                parsed["tool_calls"] = []

            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from model response: {e}")
        except Exception as ex:
            logger.error(f"Unexpected error parsing JSON response: {ex}")


        return {
            "thinking": "",
            "analysis": "",
            "tool_calls": [],
            "answer": message
        }

class DefaultFormatParser(FormatParser):


    def can_parse(self, message: str) -> bool:

        return True

    def parse(self, message: str) -> Dict[str, Any]:

        return {
            "thinking": "",
            "analysis": "",
            "tool_calls": [],
            "answer": message
        }

class ToolParser:


    def __init__(self):


        from Core.formats import AnthropicToolsParser, DeepseekToolsParser, XMLFormatParser

        self.parsers: List[FormatParser] = [
            AnthropicToolsParser(),
            DeepseekToolsParser(),
            XMLFormatParser(),
            JSONFormatParser(),
            CLIFormatParser(),
            DefaultFormatParser()
        ]

    def register_parser(self, parser: FormatParser):

        self.parsers.insert(-1, parser)

    def parse_message(self, message: str) -> Dict[str, Any]:

        for parser in self.parsers:
            if parser.can_parse(message):
                return parser.parse(message)


        return {
            "thinking": "",
            "analysis": "",
            "tool_calls": [],
            "answer": message
        }

    @staticmethod
    def extract_tool_calls(message: str) -> List[Tuple[str, Dict[str, str], bool]]:

        return CLIFormatParser().extract_tool_calls(message)
