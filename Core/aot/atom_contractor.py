"""
Atom contractor for Atom of Thoughts (AoT) module.

This component contracts atom results into a final response.
"""

import logging
import asyncio
from typing import Dict, List, Any
from Core.aot.atom_types import AtomResult, AtomStatus

logger = logging.getLogger(__name__)

class AtomContractor:
    """Contracts atom results into a final response"""
    
    def __init__(self, llm_client, config=None):
        self.llm = llm_client
        self.config = config or {}
        self.temperature = self.config.get('contraction', {}).get('temperature', 0.3)
        self.include_atom_content = self.config.get('contraction', {}).get('include_atom_content', True)
        
        # Load prompts
        from Core.aot.prompts.contraction import CONTRACTION_PROMPT_TEMPLATE
        self.prompt_template = CONTRACTION_PROMPT_TEMPLATE
    
    async def contract_atoms(
        self,
        atom_results: Dict[str, AtomResult],
        user_query: str,
        conversation_history: List[Dict[str, str]]
    ) -> str:
        """
        Contract atom results into a single coherent response.
        
        Args:
            atom_results: Dictionary mapping atom IDs to their results
            user_query: The original user query
            conversation_history: Recent conversation history for context
            
        Returns:
            A coherent final response to the user
        """
        logger.info(f"Contracting {len(atom_results)} atom results")
        
        try:
            # Format the contraction prompt
            prompt = self._format_contraction_prompt(atom_results, user_query, conversation_history)
            
            # Use different temperature for contraction
            original_temp = getattr(self.llm, 'temperature', None)
            if hasattr(self.llm, 'temperature') and original_temp is not None:
                self.llm.temperature = self.temperature
                
            try:
                # Request contraction from LLM
                contraction_conversation = [
                    {"role": "system", "content": "You are synthesizing information from multiple thought components into a coherent response."},
                    {"role": "user", "content": prompt}
                ]
                
                response = await self.llm.generate_response(contraction_conversation)
                return response
                
            finally:
                # Restore original temperature
                if hasattr(self.llm, 'temperature') and original_temp is not None:
                    self.llm.temperature = original_temp
                    
        except Exception as e:
            logger.error(f"Error in atom contraction: {e}")
            
            # Fallback: use the content from the final atom
            completed_atoms = [r for r in atom_results.values() if r.status == AtomStatus.COMPLETED]
            if completed_atoms:
                # Sort by atom ID to get a deterministic result
                sorted_atoms = sorted(completed_atoms, key=lambda x: x.atom_id)
                return sorted_atoms[-1].content
            
            # Extreme fallback
            return f"I apologize, but I had difficulty processing your request due to a technical error: {str(e)}"
    
    def _format_contraction_prompt(
        self,
        atom_results: Dict[str, AtomResult],
        user_query: str,
        conversation_history: List[Dict[str, str]]
    ) -> str:
        """Format the prompt for result contraction"""
        # Extract successful results
        successful_results = {
            atom_id: result 
            for atom_id, result in atom_results.items() 
            if result.status == AtomStatus.COMPLETED
        }
        
        # Format results section
        results_text = ""
        for atom_id, result in successful_results.items():
            content = result.content
            # Truncate very long contents
            if len(content) > 1000:
                content = content[:997] + "..."
                
            results_text += f"RESULT FROM {atom_id}:\n{content}\n\n"
            
        # Extract context
        context = self._extract_context(conversation_history)
        
        # Format the final prompt
        return self.prompt_template.format(
            user_query=user_query,
            context=context,
            atom_results=results_text,
            result_count=len(successful_results)
        )
    
    def _extract_context(self, conversation_history: List[Dict[str, str]]) -> str:
        """Extract relevant context from conversation history"""
        if not conversation_history:
            return ""
            
        # For simplicity, use the last few exchanges
        recent_history = conversation_history[-4:] if len(conversation_history) > 4 else conversation_history
        context_parts = []
        
        for msg in recent_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role and content:
                prefix = "User: " if role == "user" else "Assistant: "
                context_parts.append(f"{prefix}{content}")
        
        return "\n\n".join(context_parts)