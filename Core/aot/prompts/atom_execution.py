"""
Atom execution prompt for Atom of Thoughts (AoT) module.
"""

ATOM_EXECUTION_TEMPLATE = """
# Atom Execution

## Context
{context}

## Atom Information
- Type: {atom_type}
- Description: {atom_description}
- Query: {atom_query}

## Dependencies
{dependencies}

## Instructions
This is a single unit of thought processing. Focus exclusively on this specific aspect of the problem.
1. Consider the context and dependencies provided
2. Address only the query for this specific atom
3. Provide a clear, focused response that directly addresses the atom's purpose
4. Do not try to address the overall user query - focus only on this atom's specific task

## Response Format
Provide a concise, targeted response that could be combined with other atoms' results later.
"""