"""
Contraction prompt for Atom of Thoughts (AoT) module.
"""

CONTRACTION_PROMPT_TEMPLATE = """
# Results Synthesis

## Original User Query
{user_query}

## Context
{context}

## Atom Results
{atom_results}

## Instructions
Synthesize the results from {result_count} different thought atoms into a single, coherent response to the user's original query.

1. Consider all atom results, giving appropriate weight to each
2. Ensure your response directly addresses the user's query
3. Integrate insights from all relevant atoms
4. Resolve any apparent contradictions between atom results
5. Present a unified, coherent response that appears as a single stream of thought
6. Format the response appropriately for the user's needs (code, explanations, etc.)

DO NOT mention atoms, thought processes, or decomposition in your response. The user should not be aware of the atom-based processing.

## Response Format
Provide a complete response to the user's query as if you had generated it directly.
"""