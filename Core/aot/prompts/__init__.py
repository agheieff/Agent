"""
Prompt templates for Atom of Thoughts (AoT) module.
"""

from Core.aot.prompts.decomposition import DECOMPOSITION_PROMPT_TEMPLATE
from Core.aot.prompts.atom_execution import ATOM_EXECUTION_TEMPLATE
from Core.aot.prompts.contraction import CONTRACTION_PROMPT_TEMPLATE

__all__ = [
    "DECOMPOSITION_PROMPT_TEMPLATE",
    "ATOM_EXECUTION_TEMPLATE",
    "CONTRACTION_PROMPT_TEMPLATE",
]