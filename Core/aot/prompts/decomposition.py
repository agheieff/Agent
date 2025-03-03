"""
Decomposition prompt for Atom of Thoughts (AoT) module.
"""

DECOMPOSITION_PROMPT_TEMPLATE = """
# Task Decomposition

## Context
{context}

## User Query
{user_query}

## Instructions
Break down the user's query into smaller, atomic thoughts that can be processed independently. Each atom should:
1. Focus on a specific aspect of the problem
2. Be individually addressable
3. Have clear dependencies on other atoms, if any

Create up to {max_atoms} atoms (can be fewer if appropriate).

## Expected Output Format
Provide the decomposition as a JSON object with the following format:

```json
{{
  "atoms": [
    {{
      "id": "atom_1",
      "type": "RESEARCH",
      "description": "Brief description of what this atom should do",
      "inputs": [],
      "query": "Specific directive for this atom"
    }},
    {{
      "id": "atom_2",
      "type": "ANALYSIS",
      "description": "Brief description of what this atom should do",
      "inputs": ["atom_1"],
      "query": "Specific directive for this atom, building on atom_1"
    }}
    // Add more atoms as needed
  ]
}}
```

Valid atom types: RESEARCH, ANALYSIS, SYNTHESIS, VERIFICATION, PLANNING

## Special Cases
- If the query is simple, you may create just 1-2 atoms
- For complex problems, create more atoms with clear dependencies
- Ensure there are no circular dependencies between atoms

Now, decompose the user query into appropriate atoms:
"""