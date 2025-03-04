"""
Additional format handlers for the agent.

This module contains implementations for various format handlers
that can be plugged into the parser and composer components.
"""

import logging
import json
import xml.dom.minidom
import xml.etree.ElementTree as ET
import re
from typing import List, Dict, Any, Tuple, Optional
from xml.sax.saxutils import escape as xml_escape

from Core.parser import FormatParser
from Core.composer import FormatComposer

logger = logging.getLogger(__name__)

class XMLFormatParser(FormatParser):


    def can_parse(self, message: str) -> bool:

        message = message.strip()
        return message.startswith('<') and message.endswith('>')

    def parse(self, message: str) -> Dict[str, Any]:

        try:

            root = ET.fromstring(message.strip())


            if root.tag != 'agent_response':
                logger.warning(f"XML root element is not 'agent_response', found '{root.tag}'")


            thinking_elem = root.find('thinking')
            thinking = thinking_elem.text if thinking_elem is not None else ""

            analysis_elem = root.find('analysis')
            analysis = analysis_elem.text if analysis_elem is not None else ""

            answer_elem = root.find('answer')
            answer = answer_elem.text if answer_elem is not None else ""


            tool_calls = []
            tools_elem = root.find('tool_calls')

            if tools_elem is not None:
                for tool_elem in tools_elem.findall('tool'):
                    name = tool_elem.get('name', '')
                    is_help = tool_elem.get('help', 'false').lower() == 'true'


                    params = {}
                    params_elem = tool_elem.find('params')
                    if params_elem is not None:
                        for param in params_elem.findall('param'):
                            param_name = param.get('name', '')
                            param_value = param.text or ''
                            if param_name:
                                params[param_name] = param_value

                    tool_calls.append({
                        "name": name,
                        "params": params,
                        "help": is_help
                    })

            return {
                "thinking": thinking,
                "analysis": analysis,
                "tool_calls": tool_calls,
                "answer": answer
            }

        except ET.ParseError as e:
            logger.error(f"Failed to parse XML: {e}")
        except Exception as ex:
            logger.error(f"Unexpected error parsing XML: {ex}")


        return {
            "thinking": "",
            "analysis": "",
            "tool_calls": [],
            "answer": message
        }

class XMLFormatComposer(FormatComposer):


    def format_tool_result(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any]) -> str:

        root = ET.Element('tool_result')


        name_elem = ET.SubElement(root, 'name')
        name_elem.text = tool_name


        params_elem = ET.SubElement(root, 'params')
        for key, value in params.items():
            param = ET.SubElement(params_elem, 'param', {'name': key})
            if isinstance(value, str):
                param.text = value
            else:
                param.text = str(value)


        status_elem = ET.SubElement(root, 'status')
        success = result.get("success", False)
        status_elem.text = 'success' if success else 'failure'


        error = result.get("error", "")
        if error:
            error_elem = ET.SubElement(root, 'error')
            error_elem.text = error


        output = result.get("output", "")
        if output:
            output_elem = ET.SubElement(root, 'output')
            output_elem.text = output


        exit_code = result.get("exit_code", 1 if not success else 0)
        exit_code_elem = ET.SubElement(root, 'exit_code')
        exit_code_elem.text = str(exit_code)


        xml_str = ET.tostring(root, encoding='unicode')
        dom = xml.dom.minidom.parseString(xml_str)
        return dom.toprettyxml(indent="  ")

    def compose_response(self, tool_results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:

        root = ET.Element('tool_results')

        if not tool_results:
            message = ET.SubElement(root, 'message')
            message.text = "No tools were executed."

            xml_str = ET.tostring(root, encoding='unicode')
            dom = xml.dom.minidom.parseString(xml_str)
            return dom.toprettyxml(indent="  ")


        for tool_name, params, result in tool_results:

            result_xml = self.format_tool_result(tool_name, params, result)


            result_elem = ET.fromstring(result_xml)
            root.append(result_elem)


        message = ET.SubElement(root, 'message')
        message.text = "Tool execution complete."


        xml_str = ET.tostring(root, encoding='unicode')
        dom = xml.dom.minidom.parseString(xml_str)
        return dom.toprettyxml(indent="  ")

class AnthropicToolsParser(FormatParser):


    def can_parse(self, message: str) -> bool:


        if not isinstance(message, str):
            return False


        return bool(re.search(r'tool_use\s*:\s*{', message, re.DOTALL))

    def parse(self, message: str) -> Dict[str, Any]:

        try:
            tool_calls = []


            tool_use_pattern = r'tool_use\s*:\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})'
            matches = re.finditer(tool_use_pattern, message, re.DOTALL)

            for match in matches:
                tool_json_str = match.group(1)
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


            return {
                "thinking": "",
                "analysis": "",
                "tool_calls": tool_calls,
                "answer": ""
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


    def can_parse(self, message: str) -> bool:

        try:
            if not isinstance(message, str):
                return False


            data = json.loads(message.strip())

            return (isinstance(data, dict) and
                    "action" in data and
                    (("action_input" in data) or ("parameters" in data)))
        except (json.JSONDecodeError, AttributeError):
            return False

    def parse(self, message: str) -> Dict[str, Any]:

        try:
            data = json.loads(message.strip())


            tool_name = data.get("action", "")


            params = data.get("action_input", {})
            if not params and "parameters" in data:
                params = data.get("parameters", {})


            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:

                    params = {"value": params}


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
