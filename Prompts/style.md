# Arcadia Agent - Code Style & Architecture Guidelines

## Core Architecture Principles

1. **Format Agnosticism**: The agent should support multiple input/output formats (JSON, CLI, XML, etc.) without changing core functionality.
2. **Separation of Concerns**: Clearly separate parsing, execution, and response formatting.
3. **Extensibility**: Adding new tools or formats should require minimal changes to existing code.
4. **Configurability**: Everything that might change should be configurable.

## Component Responsibilities

### Parser Component
- **Single Responsibility**: Convert any command format into a standardized internal representation.
- **Interface Contracts**: Must extract tool name, parameters, help flag, and other metadata from input.
- **Format Support**: Should be able to parse different formats (JSON, CLI, etc.) via pluggable format handlers.
- **Error Handling**: Gracefully handle malformed input with meaningful error messages.

### Composer Component
- **Single Responsibility**: Format tool execution results into the desired output format.
- **Format Support**: Should be able to output in different formats (text, JSON, XML, etc.).
- **Consistent Structure**: Results should have a consistent structure regardless of format.
- **Error Formatting**: Properly format error messages and status codes.

### Tool Component
- **Standard Interface**: All tools should implement a consistent interface.
- **Self-Documentation**: Tools should define their own metadata (name, description, usage, examples).
- **Parameter Validation**: Tools should validate their own parameters.
- **Stateless Execution**: Tools should be stateless and not rely on external state.

### Agent Component
- **Orchestration**: Coordinate parsing, tool execution, and result composition.
- **State Management**: Maintain conversation history and agent state.
- **Format Detection**: Automatically detect and handle different input formats.
- **Configurability**: Allow configuration of behavior via settings.

## Example Generation

1. **Parameter-Based Examples**: Examples should be generated programmatically from parameter definitions.
2. **Consistency**: Example format should match the expected input format.
3. **Coverage**: Examples should cover common use cases and edge cases.
4. **Documentation**: Examples should be documented with expected output.

## Format Handlers

To add a new format (e.g., XML instead of JSON), you would:

1. Create a new format handler in the Parser component.
2. Create a matching formatter in the Composer component.
3. Update the format detection logic in the Agent component.
4. No changes needed to individual tools.

## Implementation Guidelines

1. **Type Hints**: Use Python type hints for all function parameters and return values.
2. **Documentation**: Document all classes, methods, and functions with docstrings.
3. **Error Handling**: Use consistent error handling patterns throughout the codebase.
4. **Testing**: Write tests for each format handler and ensure all tools work with all formats.
5. **Configuration**: Use a centralized configuration system for all configurable parameters.

## LLM Instructions

When responding to user requests:

1. Parse the user's message to identify intent.
2. Convert the message to the standardized internal format.
3. Execute the appropriate tool(s) based on the standardized format.
4. Format the results according to the user's preferred output format.
5. Return the formatted results to the user.

Multiple formats can be supported by:
- Detecting the format in the user's message
- Using format-specific parsers to convert to internal representation
- Using format-specific formatters to convert back to the user's preferred format

This approach ensures that the core functionality remains unchanged regardless of the input/output format.