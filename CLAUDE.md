# Agent Refactoring Plan

## Testing Commands
- Run agent: `python run_agent.py`
- Run agent in test mode: `python run_agent.py --test`
- Run with specific provider: `python run_agent.py --provider anthropic`
- Run with specific model: `python run_agent.py --model claude-3-7-sonnet`
- Run with both: `python run_agent.py --provider anthropic --model claude-3-sonnet`

## Codebase Structure
The Agent codebase has redundant implementations and inconsistent interfaces. This refactoring plan addresses these issues.

## Changes Completed

1. Standardized import paths:
   - Added proper imports in `Clients/__init__.py`
   - Added proper imports in `Memory/__init__.py`
   - Updated imports in `Core/agent.py` with comments

2. Fixed memory management:
   - Added missing methods to `Memory/Manager/memory_manager.py`
   - Added compatibility properties for consistent interface
   - Implemented robust memory operations tracking

3. Fixed system prompt paths:
   - Updated paths in `Core/agent.py` to use proper relative paths
   - Updated paths in `run_agent.py` to use consistent path resolution

4. Improved model selection UI:
   - Added detection of available API keys
   - Implemented two-step model selection (provider then model)
   - Added provider-aware command line arguments
   - Shows specific error messages when no API keys are found

5. DeepSeek-specific handling:
   - For DeepSeek models, combined system prompt with user prompt
   - Added empty system prompt to avoid DeepSeek's system prompt bugs

6. Consolidated memory components:
   - Moved `Core/memory_cache.py` to `Memory/Cache/memory_cache.py`
   - Moved `Core/memory_preloader.py` to `Memory/Preloader/memory_preloader.py`
   - Updated imports in `Core/agent.py` to use new paths
   - Updated `Memory/__init__.py` to include new components

## Refactoring Plan (Remaining)

### Phase 1: Directory Structure Consolidation ✅

1. Standardize on uppercase `Core` directory ✅
2. Consolidate memory components: ✅
   - Move related components from `Core` to appropriate subdirectories in `Memory` ✅
   - Update imports and references ✅
   - Created Memory/Cache and Memory/Preloader subdirectories ✅

### Phase 2: Component Consolidation

1. LLM Clients Consolidation:
   - Merge duplicate implementations between `Core/llm_client/` and `Clients/LLM/`
   - Standardize on `Clients/LLM` implementation
   - Update all imports and references

2. Memory Managers Consolidation:
   - Merge functionality between `Core/memory_manager.py` and `Memory/Manager/memory_manager.py`
   - Preserve advanced capabilities from Core implementationYq
   - Standardize on modular approach with components in `Memory/*` subdirectories

3. Tool Implementations Standardization:
   - Organize all tools consistently under `Tools/` directory
   - Update imports and references

### Phase 3: Interface Standardization

1. Define Base Interfaces:
   - Create abstract base classes for major components
   - Standardize parameter names and return types

2. API Standardization:
   - Normalize error handling and logging approaches
   - Document public API interfaces

3. Configuration Standardization:
   - Centralize configuration in `Config/`
   - Use dependency injection for component configuration

### Phase 4: Fix Partially Implemented Features

1. Command Manager Implementation:
   - Complete implementation of `CommandManager` class
   - Standardize command processing

2. Memory Preloader Enhancement:
   - Complete implementation of `MemoryPreloader`
   - Fix missing command_manager issue

3. Session Management Completion:
   - Enhance `SessionManager` integration
   - Fix persistence and recovery mechanisms

### Phase 5: Integration Testing

1. Create test harness
2. Implement regression tests for fixed issues
