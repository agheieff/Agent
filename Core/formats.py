
import logging
import json
import re
from typing import List, Dict, Any, Tuple, Optional

from Core.parser import FormatParser
from Core.composer import FormatComposer

logger = logging.getLogger(__name__)

class AnthropicToolsParser(FormatParser):
    def can_parse(self, message: str) -> bool:
        """Check if the message is in Claude's tool use format"""
        if not isinstance(message, str):
            return False
            
        # Look for tool_use format
        tool_use_pattern = r'<tool_use>|tool_use\s*:'
        return bool(re.search(tool_use_pattern, message, re.DOTALL))

    def parse(self, message: str) -> Dict[str, Any]:
        """Parse a message in Claude's tool use format"""
        try:
            tool_calls = []
            thinking = ""
            analysis = ""
            answer = ""
            
            # Extract answer if present
            answer_match = re.search(r'<answer>(.*?)</answer>', message, re.DOTALL)
            if answer_match:
                answer = answer_match.group(1).strip()
            
            # Try both the XML-like patterns
            # First, the tag-based pattern 
            tool_use_match = re.search(r'<tool_use>(.*?)</tool_use>', message, re.DOTALL)
            if tool_use_match:
                tool_json_str = tool_use_match.group(1).strip()
                try:
                    tool_data = json.loads(tool_json_str)
                    if "name" in tool_data:
                        tool_calls.append({
                            "name": tool_data.get("name", ""),
                            "params": tool_data.get("input", {}),
                            "help": False
                        })
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse tool use JSON: {tool_json_str}")
            
            # Try the colon-based pattern
            tool_use_pattern = r'tool_use\s*:\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})'
            matches = re.finditer(tool_use_pattern, message, re.DOTALL)
            for match in matches:
                tool_json_str = match.group(1)
                try:
                    tool_data = json.loads(tool_json_str)
                    if "name" in tool_data:
                        # Only add if not already added from the tag version
                        if not tool_calls or tool_calls[0]["name"] != tool_data.get("name", ""):
                            tool_calls.append({
                                "name": tool_data.get("name", ""),
                                "params": tool_data.get("input", {}),
                                "help": False
                            })
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse tool use JSON: {tool_json_str}")

            # If no tools found and we have an answer, use the message tool
            if not tool_calls and answer:
                tool_calls.append({
                    "name": "message",
                    "params": {"text": answer},
                    "help": False
                })
                # Clear the answer since we're converting it to a message tool
                answer = ""

            return {
                "thinking": thinking,
                "analysis": analysis,
                "tool_calls": tool_calls,
                "answer": answer
            }

        except Exception as e:
            logger.error(f"Error parsing Anthropic tool use format: {e}")
            return {
                "thinking": "",
                "analysis": "",
                "tool_calls": [],
                "answer": message
            }

class DeepseekToolsParser(FormatParser):
    """
    Parser for DeepSeek's JSON format.
    
    DeepSeek's format typically looks like:
    {
      "thinking": "...",
      "reasoning": "...",
      "action": "tool_name",
      "action_input": {
        "param1": "value1"
      },
      "response": "..."
    }
    """

    def can_parse(self, message: str) -> bool:
        """Check if the message is in DeepSeek's JSON format"""
        try:
            if not isinstance(message, str):
                return False

            # Try to parse as JSON
            data = json.loads(message.strip())

            # Check if it's a dict with at least "action" key
            return (isinstance(data, dict) and
                    "action" in data and
                    (("action_input" in data) or ("parameters" in data)))
        except (json.JSONDecodeError, AttributeError):
            return False

    def parse(self, message: str) -> Dict[str, Any]:
        """Parse a message in DeepSeek's JSON format"""
        try:
            data = json.loads(message.strip())

            # Get the tool name
            tool_name = data.get("action", "")

            # Get parameters (DeepSeek might use "action_input" or "parameters")
            params = data.get("action_input", {})
            if not params and "parameters" in data:
                params = data.get("parameters", {})

            # If params is a string, try to parse it as JSON
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:
                    # If it's not valid JSON, treat it as a single value
                    params = {"value": params}

            # If no tool is specified but there is a response, use the message tool
            if not tool_name and "response" in data:
                tool_name = "message"
                params = {"text": data.get("response", "")}

            return {
                "thinking": data.get("thinking", ""),
                "analysis": data.get("reasoning", ""),
                "tool_calls": [{
                    "name": tool_name,
                    "params": params,
                    "help": False
                }] if tool_name else [],
                "answer": data.get("response", "")
            }

        except Exception as e:
            logger.error(f"Error parsing Deepseek tool use format: {e}")
            return {
                "thinking": "",
                "analysis": "",
                "tool_calls": [],
                "answer": message
            }

class OpenAIToolsParser(FormatParser):
    """
    Parser for OpenAI's JSON format.
    
    OpenAI's format typically looks like:
    {
      "thinking": "...",
      "analysis": "...",
      "tool_calls": [{
        "name": "tool_name",
        "params": {
          "param1": "value1"
        }
      }],
      "answer": "..."
    }
    """

    def can_parse(self, message: str) -> bool:
        """Check if the message is in OpenAI's JSON format"""
        try:
            if not isinstance(message, str):
                return False

            # Try to parse as JSON
            data = json.loads(message.strip())

            # Check if it has the expected structure
            return (isinstance(data, dict) and
                    ("tool_calls" in data or 
                     "function_call" in data or
                     "function_calls" in data))
        except (json.JSONDecodeError, AttributeError):
            return False

    def parse(self, message: str) -> Dict[str, Any]:
        """Parse a message in OpenAI's JSON format"""
        try:
            data = json.loads(message.strip())
            
            # Initialize the structure
            parsed = {
                "thinking": data.get("thinking", ""),
                "analysis": data.get("analysis", ""),
                "tool_calls": [],
                "answer": data.get("answer", "")
            }
            
            # Handle tool_calls
            if "tool_calls" in data and isinstance(data["tool_calls"], list):
                parsed["tool_calls"] = data["tool_calls"]
            
            # Handle function_call (OpenAI native format)
            elif "function_call" in data:
                function_call = data["function_call"]
                name = function_call.get("name", "")
                arguments = function_call.get("arguments", "{}")
                
                try:
                    args = json.loads(arguments)
                except json.JSONDecodeError:
                    args = {"value": arguments}
                    
                if name:
                    parsed["tool_calls"].append({
                        "name": name,
                        "params": args,
                        "help": False
                    })
            
            # Handle function_calls (plural) if present
            elif "function_calls" in data and isinstance(data["function_calls"], list):
                for func_call in data["function_calls"]:
                    name = func_call.get("name", "")
                    arguments = func_call.get("arguments", "{}")
                    
                    try:
                        args = json.loads(arguments)
                    except json.JSONDecodeError:
                        args = {"value": arguments}
                        
                    if name:
                        parsed["tool_calls"].append({
                            "name": name,
                            "params": args,
                            "help": False
                        })
            
            # If no tool calls found but there's an answer, convert to message
            if not parsed["tool_calls"] and parsed["answer"]:
                parsed["tool_calls"].append({
                    "name": "message",
                    "params": {"text": parsed["answer"]},
                    "help": False
                })
                parsed["answer"] = ""
                
            return parsed

        except Exception as e:
            logger.error(f"Error parsing OpenAI JSON format: {e}")
            return {
                "thinking": "",
                "analysis": "",
                "tool_calls": [],
                "answer": message
            }

class JSONFormatParser(FormatParser):
    """
    Generic JSON format parser.
    
    Parses standard JSON format:
    {
      "thinking": "...",
      "analysis": "...",
      "tool_calls": [{
        "name": "tool_name",
        "params": {
          "param1": "value1"
        }
      }],
      "answer": "..."
    }
    """

    def can_parse(self, message: str) -> bool:
        """Check if the message is in JSON format"""
        message = message.strip()
        return (message.startswith('{') and message.endswith('}')) or \
               (message.startswith('[') and message.endswith(']'))

    def parse(self, message: str) -> Dict[str, Any]:
        """Parse a message in JSON format"""
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

            # Validate tool_calls is a list
            if not isinstance(parsed["tool_calls"], list):
                logger.warning("tool_calls is not a list; forcing it to be an empty list.")
                parsed["tool_calls"] = []
                
            # If no tool calls but there's an answer, convert to message tool
            if not parsed["tool_calls"] and parsed["answer"]:
                parsed["tool_calls"].append({
                    "name": "message",
                    "params": {"text": parsed["answer"]},
                    "help": False
                })
                parsed["answer"] = ""

            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from model response: {e}")
        except Exception as ex:
            logger.error(f"Unexpected error parsing JSON response: {ex}")

        # Return default structure if parsing fails
        return {
            "thinking": "",
            "analysis": "",
            "tool_calls": [],
            "answer": message
        }
