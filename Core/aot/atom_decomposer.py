"""
Atom decomposer for Atom of Thoughts (AoT) module.

This component decomposes a user query into atomic thought components.
"""

import logging
import asyncio
import json
import re
from typing import List, Dict, Any, Optional

from Core.aot.atom_types import Atom, AtomType

logger = logging.getLogger(__name__)

class AtomDecomposer:
    """Decomposes a problem into atomic thought components"""
    
    def __init__(self, llm_client, config=None):
        self.llm = llm_client
        self.config = config or {}
        self.max_atoms = self.config.get('decomposition', {}).get('max_atoms', 8)
        self.temperature = self.config.get('decomposition', {}).get('temperature', 0.7)
        self.max_depth = self.config.get('decomposition', {}).get('max_depth', 3)
        
        # Load prompts
        from Core.aot.prompts.decomposition import DECOMPOSITION_PROMPT_TEMPLATE
        self.prompt_template = DECOMPOSITION_PROMPT_TEMPLATE
    
    async def decompose(self, user_query: str, conversation_history: List[Dict[str, str]]) -> List[Atom]:
        """
        Decompose a problem into atomic components that can be solved individually.
        
        Args:
            user_query: The user's question or request
            conversation_history: Previous conversation for context
            
        Returns:
            List of Atom objects representing the decomposed problem
        """
        try:
            # Format the prompt for decomposition
            context = self._extract_context(conversation_history)
            prompt = self.prompt_template.format(
                context=context,
                user_query=user_query,
                max_atoms=self.max_atoms
            )
            
            # Request decomposition from LLM
            decomposition_response = await self._get_decomposition(prompt)
            
            # Parse the response into Atom objects
            atoms = self._parse_atoms(decomposition_response, user_query)
            
            logger.info(f"Decomposed problem into {len(atoms)} atoms")
            return atoms
            
        except Exception as e:
            logger.error(f"Error decomposing problem: {e}")
            # Return a single atom as fallback
            return [Atom(
                id="atom_1",
                type=AtomType.SYNTHESIS,
                description="Answer the user query directly",
                inputs=[],
                query=user_query
            )]
    
    def _extract_context(self, conversation_history: List[Dict[str, str]]) -> str:
        """Extract relevant context from the conversation history"""
        if not conversation_history:
            return ""
            
        # For simplicity, use the last few exchanges
        recent_history = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
        context_parts = []
        
        for msg in recent_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role and content:
                prefix = "User: " if role == "user" else "Assistant: "
                context_parts.append(f"{prefix}{content}")
        
        return "\n\n".join(context_parts)
    
    async def _get_decomposition(self, prompt: str) -> str:
        """Request decomposition from LLM"""
        # Create a minimal conversation with just the decomposition prompt
        conversation = [
            {"role": "system", "content": "You are an expert at breaking down complex problems into simpler atomic components."},
            {"role": "user", "content": prompt}
        ]
        
        # Use different temperature for decomposition
        original_temp = getattr(self.llm, 'temperature', None)
        if hasattr(self.llm, 'temperature') and original_temp is not None:
            self.llm.temperature = self.temperature
            
        try:
            response = await self.llm.generate_response(conversation)
            return response
        finally:
            # Restore original temperature
            if hasattr(self.llm, 'temperature') and original_temp is not None:
                self.llm.temperature = original_temp
    
    def _parse_atoms(self, decomposition_response: str, user_query: str) -> List[Atom]:
        """Parse the LLM response into structured Atom objects"""
        atoms = []
        
        # Try to extract JSON from the response
        try:
            # Look for JSON block in markdown format
            json_match = re.search(r'```json\n(.*?)\n```', decomposition_response, re.DOTALL)
            
            # If not found, try without markdown formatting
            if not json_match:
                json_match = re.search(r'({[\s\S]*"atoms"[\s\S]*})', decomposition_response)
            
            if json_match:
                atoms_json = json.loads(json_match.group(1))
                
                # Convert to Atom objects
                for i, atom_data in enumerate(atoms_json.get("atoms", [])):
                    atom_id = atom_data.get("id", f"atom_{i+1}")
                    atom_type_str = atom_data.get("type", "SYNTHESIS").upper()
                    
                    # Parse atom type
                    try:
                        atom_type = AtomType[atom_type_str]
                    except (KeyError, AttributeError):
                        atom_type = AtomType.SYNTHESIS
                    
                    atom = Atom(
                        id=atom_id,
                        type=atom_type,
                        description=atom_data.get("description", f"Step {i+1}"),
                        inputs=atom_data.get("inputs", []),
                        query=atom_data.get("query", f"Process part {i+1} of: {user_query}")
                    )
                    atoms.append(atom)
            else:
                # If no JSON found, try parsing manually
                logger.warning("No JSON found in decomposition response, attempting manual parsing")
                sections = re.split(r'\n(?=Atom \d+:|\d+\.)', decomposition_response)
                
                for i, section in enumerate(sections):
                    if not section.strip():
                        continue
                        
                    # Extract description and query
                    desc_match = re.search(r'(?:Description|Task):(.*?)(?:(?:Type|Query|Inputs):|$)', section, re.DOTALL)
                    description = desc_match.group(1).strip() if desc_match else f"Step {i+1}"
                    
                    query_match = re.search(r'Query:(.*?)(?:(?:Inputs|Type):|$)', section, re.DOTALL)
                    query = query_match.group(1).strip() if query_match else f"Process part {i+1} of: {user_query}"
                    
                    # Extract dependencies
                    inputs = []
                    inputs_match = re.search(r'Inputs:(.*?)(?:(?:Type|Query):|$)', section, re.DOTALL)
                    if inputs_match:
                        inputs_text = inputs_match.group(1)
                        # Extract atom IDs like atom_1, atom_2, etc.
                        input_ids = re.findall(r'atom_\d+', inputs_text)
                        if input_ids:
                            inputs = input_ids
                    
                    atom = Atom(
                        id=f"atom_{i+1}",
                        type=AtomType.SYNTHESIS,  # Default to synthesis
                        description=description,
                        inputs=inputs,
                        query=query
                    )
                    atoms.append(atom)
                
        except Exception as e:
            logger.error(f"Error parsing atoms from decomposition: {e}")
        
        # Ensure we have at least one atom
        if not atoms:
            atoms = [Atom(
                id="atom_1",
                type=AtomType.SYNTHESIS,
                description="Answer the user query directly",
                inputs=[],
                query=user_query
            )]
        
        return atoms