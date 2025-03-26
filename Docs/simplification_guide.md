# Arcadia Agent Simplification Guide

This document outlines specific patterns and strategies for simplifying the Arcadia Agent codebase while preserving functionality.

## General Principles

1. **Don't Repeat Yourself (DRY)** - Eliminate code duplication through inheritance, composition, and utility functions
2. **Single Responsibility Principle** - Each class/method should have one clear purpose
3. **Composition Over Inheritance** - Use composition for flexibility when appropriate
4. **Fail Fast** - Validate inputs early and provide clear error messages
5. **Keep It Simple** - Avoid unnecessary abstractions and complexity

## Specific Simplification Patterns

### 1. Error Handling Standardization

#### Current Pattern
```python
try:
    # Operation that might fail
    result = some_operation()
except SomeError as e:
    # Log and return error response
    logger.error(f"Error occurred: {e}")
    return ErrorResponse(...)
```

#### Improved Pattern
```python
# Define error handling once in a decorator or context manager
@handle_operation_errors
def perform_operation():
    # Operation that might fail
    return some_operation()
```

### 2. Model Configuration Consolidation

#### Current Pattern
```python
PROVIDER_CONFIG = ProviderConfig(
    name="provider",
    api_base="https://api.provider.com",
    api_key_env="PROVIDER_API_KEY",
    # Repeated model definitions in different files
    models={
        "model-a": ModelConfig(...),
        "model-b": ModelConfig(...),
    }
)
```

#### Improved Pattern
```python
# models.py - Centralized model registry
MODEL_REGISTRY = {
    "provider1": {
        "model-a": ModelConfig(...),
        "model-b": ModelConfig(...),
    },
    "provider2": {
        "model-c": ModelConfig(...),
    }
}

# provider_config.py - Reference models from registry
def get_provider_config(provider_name):
    return ProviderConfig(
        name=provider_name,
        # Other standard config
        models=MODEL_REGISTRY.get(provider_name, {})
    )
```

### 3. Client Method Standardization

#### Current Pattern
```python
# Different implementations with similar structure in each provider client
async def chat_completion(self, messages, model=None, **kwargs):
    # Provider-specific implementation with similar steps:
    # 1. Format messages
    # 2. Call API
    # 3. Parse response
    # 4. Handle errors
```

#### Improved Pattern
```python
# Base implementation with template method pattern
async def chat_completion(self, messages, model=None, **kwargs):
    """Standard implementation all providers can use."""
    formatted_messages = self._format_messages(messages)
    raw_response = await self._call_provider_api(formatted_messages, model, **kwargs)
    return self._process_response(raw_response)

# Provider-specific implementations only need to implement the private methods
def _format_messages(self, messages):
    """Provider-specific formatting."""
    
def _call_provider_api(self, formatted_messages, model, **kwargs):
    """Provider-specific API call."""
    
def _process_response(self, raw_response):
    """Provider-specific response processing."""
```

### 4. Configuration Validation

#### Current Pattern
```python
# Validation scattered throughout code
if not self.api_key:
    raise ValueError(f"API key not found in environment variable {self.config.api_key_env}")

if not mcp_server_url:
    logger.error("MCP_SERVER_URL not provided.")
    return ErrorResponse(...)
```

#### Improved Pattern
```python
def validate_config(config):
    """Centralized validation function."""
    validations = [
        (config.api_key, f"API key not found in environment variable {config.api_key_env}"),
        (config.mcp_server_url, "MCP server URL not provided"),
        # Other validations
    ]
    
    for value, error_message in validations:
        if not value:
            raise ConfigurationError(error_message)
```

### 5. Standardized Logging

#### Current Pattern
```python
# Inconsistent logging patterns
logger.info(f"Executing operation '{operation_name}'...")
# Later
logger.warning(f"Operation '{op_name}' failed")
```

#### Improved Pattern
```python
# Consistent, structured logging helper
def log_operation(logger, level, operation, status, **kwargs):
    """Standardized logging with consistent format."""
    message = f"Operation '{operation}' {status}"
    context = {
        "operation": operation,
        "status": status,
        **kwargs
    }
    logger.log(level, message, extra={"context": context})

# Usage
log_operation(logger, logging.INFO, operation_name, "started", request_id=request_id)
log_operation(logger, logging.WARNING, operation_name, "failed", error=str(e))
```

## Implementation Strategy

1. **Start with Core Classes** - Begin simplification with the most foundational classes
2. **One Pattern at a Time** - Implement one simplification pattern completely before moving to the next
3. **Maintain Tests** - Ensure each simplification preserves behavior with tests
4. **Document Changes** - Update comments and documentation to reflect new patterns

## Keeping Functionality Intact

To ensure functionality is preserved during simplification:

1. **Map Inputs/Outputs** - Document the expected inputs and outputs of each component
2. **Create Test Cases** - Add tests that verify behavior before changing implementation
3. **Implement Feature Flags** - Allow toggling between old and new implementations
4. **Incremental Adoption** - Gradually roll out simplifications rather than large-scale rewrites

## Next Simplification Tasks

1. **Client Base Class Improvements**
   - Remove redundant MCP error handling in provider clients
   - Standardize HTTP client initialization and cleanup
   - Implement template method pattern for chat completions

2. **Operation Argument Processing**
   - Simplify argument validation in Operation base class
   - Create reusable validators for common argument types
   - Add support for argument dependencies (when one argument depends on another)

3. **Server Handler Consolidation**
   - Combine similar exception handlers
   - Extract common response creation logic
   - Standardize request ID generation and propagation