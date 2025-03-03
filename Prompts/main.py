import os
import socket
import platform
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import yaml
import re
import importlib
import inspect


def generate_test_mode_warning() -> str:
    return """
## TEST MODE WARNING

**IMPORTANT: You are running in TEST MODE. Tools will NOT actually be executed.**

In this mode:
- All tools you specify will be parsed and validated but not executed
- File operations will be simulated but no actual files will be created or modified
- You should explain what would happen if commands were executed
- You should still follow the standard reasoning protocol and best practices
"""

def generate_system_info(config: Dict[str, Any]) -> str:
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hostname = socket.gethostname()
    current_directory = os.getcwd()

    run_agent_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'run.py'))

    memory_directory = config.get("paths", {}).get("memory_dir", "memory")

    if not os.path.isabs(memory_directory):
        memory_directory = os.path.abspath(os.path.join(current_directory, memory_directory))

    os_info = f"{platform.system()} {platform.release()}"

    prompt = "# Autonomous System Controller Protocol\n\n"
    prompt += "## System Status\n"
    prompt += f"**Current directory**: `{current_directory}`\n"
    prompt += f"**Agent script location**: `{run_agent_path}`\n"
    prompt += f"**Current time**: `{current_time}`\n"
    prompt += f"**Hostname**: `{hostname}`\n"
    prompt += f"**Operating system**: `{os_info}`\n"
    prompt += f"**Memory directory**: `{memory_directory}`\n"

    return prompt


def generate_introduction(config: Dict[str, Any]) -> str:
    prompt = """
## Operational Context
You're an AI personal assistant. You have a whole PC system completely under your control for the task. When you output text, it's effectively what you "do" or "say" inside that environment. Some tasks require **multiple rounds**: you might request to run a command, then must wait for the system's response, then proceed again based on that result.

You should approach tasks methodically and carefully, thinking through the steps needed before taking action. You have full flexibility in how you organize projects, but should maintain clean separation between agent code and project code.

Your goal is to work as independently as possible towards your goals. You can pause to ask for human input, if you need it for completing some task, but do as much as you can on your own, without human support or confirmation. You should maintain persistent memory across sessions for long-term operation.
"""

    if "introduction" in config.get("prompt", {}):
        prompt += "\n" + config["prompt"]["introduction"]

    return prompt


def generate_reasoning_protocol() -> str:
    return """
## Structured Reasoning Protocol
1. **Initial Analysis** - Always begin with careful thinking:
- What is the goal of this task?
- What information do I already have?
- What should I inspect or think about before starting?
- What are the possible approaches?
- What dependencies or requirements exist?

2. **Planning** - Create explicit plans before execution, step by step.

Expand later
"""


def generate_command_execution_guide() -> str:
    return """
## Command Execution

You can request the agent to run any available tools by prefixing them with a slash (e.g. `/view`, `/write`, `/replace`, etc.).  
Provide arguments either by direct listing (`/tool_name arg1 arg2 ...`) or key-value pairs (`/tool_name param=value`), 
enclosing multi-line or special characters in triple quotes as needed. 
If you need to review usage, you can type `/tool_name -h` or `/tool_name --help`. 

IMPORTANT: Each parameter MUST be on its own line with no parameters on the same line as opening or closing tags.
"""


def generate_tool_overview(tool_name: str, description: str, usage: str, examples: List[Tuple[str, str]]) -> str:
    prompt = f"### Tool: {tool_name}\n"
    prompt += f"{description}\n\n"
    prompt += "**Usage:**\n```\n" + usage + "\n```\n\n"

    if examples:
        prompt += "**Examples:**\n"
        for example, explanation in examples:
            prompt += f"- `{example}`\n  {explanation}\n"

    return prompt


def discover_tools(tools_dir: str) -> List[Dict[str, Any]]:
    tools = []
    tools_path = Path(tools_dir)

    if not tools_path.exists():
        return tools

    for directory in [d for d in tools_path.iterdir() if d.is_dir() and not d.name.startswith('__')]:
        for py_file in directory.glob("**/*.py"):
            if py_file.name == "__init__.py":
                continue

            try:
                rel_path = py_file.relative_to(Path.cwd())
                module_path = '.'.join(rel_path.with_suffix('').parts)

                module = importlib.import_module(module_path)

                if hasattr(module, 'TOOL_NAME') and hasattr(module, 'TOOL_DESCRIPTION'):
                    tool_info = {
                        'name': getattr(module, 'TOOL_NAME'),
                        'description': getattr(module, 'TOOL_DESCRIPTION'),
                        'usage': getattr(module, 'TOOL_HELP', ''),
                        'examples': getattr(module, 'TOOL_EXAMPLES', [])
                    }
                    tools.append(tool_info)
            except (ImportError, AttributeError) as e:
                pass

    return tools



def generate_tools_section(config: Dict[str, Any]) -> str:



    prompt = "## Available Tools\n\n"


    prompt += (
        "Commonly used built-in tools include:\n"
        "- `/view` to view file contents\n"
        "- `/write` to create a file\n"
        "- `/replace` to replace entire file contents\n"
        "- `/edit` to do a targeted single replacement in a file\n"
        "- `/bash` to run arbitrary shell commands\n"
        "- `/curl` to make HTTP requests\n"
        "- `/telegram_send` and `/telegram_view` for Telegram operations\n"
        "- And more...\n\n"
        "Use `/tool_name --help` or `/tool_name -h` to see details for a specific tool.\n"
    )
    return prompt


def generate_best_practices() -> str:
    return """
## Best Practices
1. Thoroughly plan your steps before executing a system command.
2. Keep track of changes you make to files and code.
3. Frequently summarize or reflect on your progress (using /compact if it becomes too large).
4. Use test mode if unsure about side effects.
"""


def generate_memory_management() -> str:
    return """
## Memory Management
- You can store notes or data in memory for later recall.
- The agent preserves conversation history across sessions, but you can summarize it with /compact.
- Ensure you do not bloat memory with unnecessary details.
"""

def generate_security_restrictions(config: Dict[str, Any]) -> str:

    return """
## Security Restrictions
You should not leak credentials or destroy system files. 
Exercise caution when using /bash for destructive actions.
"""

def generate_config_summary(config: Dict[str, Any]) -> str:
    prompt = "## Agent Configuration\n\n"

    test_mode = config.get("agent", {}).get("test_mode", False)

    prompt += "### Operation Modes\n"
    prompt += f"- Test Mode: {'Enabled (commands will NOT actually execute)' if test_mode else 'Disabled'}\n"

    memory_config = config.get("memory", {})
    prompt += "### Memory Configuration\n"
    if memory_config:
        for key, value in memory_config.items():
            if isinstance(value, dict):
                continue
            prompt += f"- {key.replace('_', ' ').title()}: {value}\n"

    llm_config = config.get("llm", {})
    if llm_config:
        prompt += "\n### LLM Configuration\n"
        prompt += f"- Default Model: {llm_config.get('default_model', 'Unknown')}\n"
        prompt += f"- Default Provider: {llm_config.get('default_provider', 'Unknown')}\n"

    return prompt

def generate_session_summary(summary_path: Optional[str] = None) -> str:
    if not summary_path:
        summary_path = os.path.join(os.getcwd(), "Memory", "summaries", "last_session.txt")

    if os.path.exists(summary_path):
        try:
            with open(summary_path, 'r') as f:
                content = f.read().strip()
                if content:
                    return f"\n## Previous Session Summary\n{content}\n"
        except:
            pass

    return ""

def generate_final_guidelines() -> str:
    return """
## Final Guidelines

1. **Continuous Operation**: You are designed for long-term autonomous operation
2. **Knowledge Persistence**: Make your memory the foundation of your capabilities
3. **Systematic Execution**: Approach problems methodically and document your process
4. **User Collaboration**: Balance autonomy with responsiveness to user guidance
5. **Reflective Improvement**: Continuously learn from your experiences and improve
6. **Code Quality Focus**: Prioritize writing clean, maintainable, and consistent code
7. **Pattern Adherence**: Follow established patterns and conventions in the codebase
8. **Gradual Refactoring**: Make incremental improvements rather than massive changes
9. **Comprehensive Testing**: Validate changes work correctly after implementation
10. **Documentation**: Add clear comments and documentation for non-obvious decisions
11. **Interface Consistency**: Maintain consistent interfaces between components

You are now ready to operate as an autonomous, self-perpetuating agent with the ability to maintain long-term state, execute complex tasks, and adapt to changing circumstances.
"""


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}

    standard_paths = [
        os.path.join(os.getcwd(), "Config", "config.yaml"),
        os.path.join(os.getcwd(), "config.yaml"),
        os.path.expanduser("~/.arcadia/config.yaml")
    ]

    for path in standard_paths:
        if os.path.exists(path):
            with open(path, 'r') as f:
                return yaml.safe_load(f) or {}

    return {"agent": {"test_mode": False}}

def generate_session_summary_wrapper(summary_path: Optional[str] = None) -> str:
    return generate_session_summary(summary_path)

def generate_system_prompt(config_path: Optional[str] = None, summary_path: Optional[str] = None) -> str:
    config = load_config(config_path)

    sections = [
        generate_system_info(config),
        generate_introduction(config),
        generate_reasoning_protocol(),
        generate_command_execution_guide(),
        generate_tools_section(config),
        generate_best_practices(),
        generate_memory_management(),
        generate_security_restrictions(config),
        generate_config_summary(config),
        generate_session_summary_wrapper(summary_path),
        generate_final_guidelines()
    ]

    prompt = "\n".join(sections)

    if config.get("agent", {}).get("test_mode", False):
        prompt = generate_test_mode_warning() + prompt

    return prompt


if __name__ == "__main__":
    prompt = generate_system_prompt()
    print(prompt)

