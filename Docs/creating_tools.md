# Creating a New Tool

This guide explains how to create a new tool for the Arcadia Agent framework.

## Steps to Create a New Tool

1. **Create a Python file** in the appropriate subdirectory of `Tools/`. For example, if building a network tool, you might create `Tools/Network/ping.py`.

2. **Import required classes** from the base module:
   ```python
   import os  # or other standard libraries as needed
   from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType
   ```

3. **Create a tool class** that inherits from `Tool` base class:
   ```python
   class MyNewTool(Tool):
       def __init__(self):
           config = ToolConfig(
               allowed_in_test_mode=True,  # Set appropriate config
               requires_sudo=False,
               requires_internet=False,
               timeout=None,
               max_retries=0
           )
           
           super().__init__(
               name="my_new_tool",
               description="Description of what the tool does",
               help_text="More detailed help information",
               arguments=[
                   Argument(
                       name="required_arg", 
                       arg_type=ArgumentType.STRING, 
                       description="Description of the argument"
                   ),
                   Argument(
                       name="optional_arg", 
                       arg_type=ArgumentType.INT, 
                       is_optional=True, 
                       default_value=42,
                       description="Optional argument with default value"
                   )
               ],
               config=config
           )
   ```

4. **Implement the `_execute` method** with your tool's logic:
   ```python
   def _execute(self, required_arg, optional_arg=42):
       # Your tool implementation goes here
       
       try:
           # Do something with the arguments
           result = some_operation(required_arg, optional_arg)
           
           # Return success code and optional message (None if no message)
           return ErrorCodes.SUCCESS, None
       except Exception as e:
           # Handle errors appropriately
           return ErrorCodes.OPERATION_FAILED, f"Failed to execute: {str(e)}"
   ```

5. **Create a test file** in the appropriate `Tests/` directory. For example, if you created a `Tools/Network/ping.py` tool, create `Tests/Tools/Network/test_ping.py`:
   ```python
   import unittest
   from unittest.mock import patch
   from Tools.Network.ping import MyNewTool
   from Tools.base import ErrorCodes

   class TestMyNewTool(unittest.TestCase):
       def setUp(self):
           self.tool = MyNewTool()
           
       def test_success_case(self):
           # Test successful execution
           exit_code, message = self.tool.execute("required_value")
           self.assertEqual(exit_code, ErrorCodes.SUCCESS)
           
       def test_error_case(self):
           # Test error handling
           # ...
   ```

6. **Run the tests** to verify your tool works:
   ```
   python3 test.py
   ```

## Supported Argument Types

The following argument types are supported:

| Type | Description | Example Input |
|------|-------------|---------------|
| `ArgumentType.STRING` | Text strings | `"Hello, world"` |
| `ArgumentType.BOOLEAN` | Boolean values | `"true"`, `"yes"`, `"1"` |
| `ArgumentType.INT` | Integer values | `"42"` |
| `ArgumentType.FLOAT` | Floating point values | `"3.14"` |
| `ArgumentType.FILEPATH` | File or directory paths | `"/path/to/file"` |
| `ArgumentType.DATETIME` | Date and time values | `"2023-04-05 14:30:45.123"` |

For datetime, the format is `yyyy-mm-dd hh:mm:ss.mmm` where any parts from the right can be omitted (defaulting to beginning value, like 1 for month/day, 0 for time components).

## Error Codes

Return appropriate error codes from your tools:

| Code | Constant | Description |
|------|----------|-------------|
| 0 | `ErrorCodes.SUCCESS` | Operation completed successfully |
| -1 | `ErrorCodes.TOOL_NOT_FOUND` | Tool does not exist |
| 1-9 | `ErrorCodes.GENERAL_ERROR` etc. | General errors |
| 10-29 | `ErrorCodes.INVALID_ARGUMENTS` etc. | Argument-related errors |
| 30-49 | `ErrorCodes.PERMISSION_DENIED` etc. | Permission/access errors |
| 50-69 | `ErrorCodes.RESOURCE_NOT_FOUND` etc. | Resource errors |
| 70-89 | `ErrorCodes.NETWORK_ERROR` etc. | Network errors |
| 90-99 | `ErrorCodes.INTERNAL_ERROR` etc. | Internal errors |

## Tool Configuration

Use `ToolConfig` to specify tool behavior:

| Parameter | Description |
|-----------|-------------|
| `allowed_in_test_mode` | Whether the tool can run in test mode |
| `requires_sudo` | Whether the tool requires admin privileges |
| `requires_internet` | Whether the tool needs internet access |
| `timeout` | Maximum execution time in seconds (None for no limit) |
| `max_retries` | Number of retry attempts if the tool fails |
| `id` | Optional unique identifier for async operations |
| `output` | Dictionary controlling display of output |

## Example Usage

Once implemented, your tool can be called like this:
```
@tool my_new_tool
required_arg: value
optional_arg: 10
@end
``` 