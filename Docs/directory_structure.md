# Directory Structure

## Overview

The project follows a clean, modular structure with clear separation of concerns:

```
Agent/
├── Tools/              # Main tools package
│   ├── {Category}/    # Tool categories (e.g., File, Network)
│   │   ├── {tool}.py  # Individual tool implementations
│   │   └── __init__.py
│   ├── base.py        # Base tool class definition
│   └── __init__.py
│
├── Tests/             # Test suite
│   ├── test_tools/    # Tests for tools (mirrors Tools structure)
│   │   ├── test_{category}/
│   │   │   ├── test_{tool}.py
│   │   │   └── __init__.py
│   │   └── __init__.py
│   └── __init__.py
│
├── Docs/             # Documentation
│   └── *.md         # Markdown documentation files
│
├── Requirements/     # Dependencies and requirements
│   └── *.txt        # Dependency specifications
│
├── setup.sh         # Environment setup script
└── test.py         # Test runner script
```

## Directory Details

### Tools/
The main package containing all tool implementations:
- Organized by categories (e.g., File operations, Network operations)
- Each category is a separate package
- Tools inherit from a common base class
- Standardized error handling across all tools

### Tests/
Test suite that mirrors the Tools structure:
- Each tool has corresponding test file(s)
- Maintains same hierarchy as Tools/ with "test_" prefix
- Uses Python's unittest framework
- Centralized test runner

### Docs/
Project documentation in markdown format:
- Explains project structure and conventions
- Documents tool usage and patterns
- Provides implementation guidelines

### Requirements/
Dependency management and environment specifications:
- Python package dependencies
- Version requirements
- Environment setup information

## Naming Conventions

1. Tool Implementation:
   - Categories use descriptive, singular nouns
   - Tool files use lowercase with underscores
   - Clear, action-oriented names for tools

2. Test Files:
   - Mirror Tools/ structure with "test_" prefix
   - Maintain parallel directory structure
   - One test file per tool (minimum)

3. Documentation:
   - Use markdown format
   - Clear, descriptive names
   - Topic-based organization

## Adding New Tools

When adding a new tool:
1. Identify appropriate category or create new one
2. Implement tool following base class contract
3. Create corresponding test structure
4. Update relevant documentation
5. Ensure package structure is maintained (__init__.py files) 