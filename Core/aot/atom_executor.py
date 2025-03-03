"""
Atom executor for Atom of Thoughts (AoT) module.

This component executes individual atoms and manages their dependencies.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Set, Tuple
from Core.aot.atom_types import Atom, AtomDAG, AtomResult, AtomStatus

logger = logging.getLogger(__name__)

class AtomExecutor:
    """Executes individual atoms and manages their dependencies"""
    
    def __init__(self, llm_client, config=None):
        self.llm = llm_client
        self.config = config or {}
        self.max_concurrent = self.config.get('execution', {}).get('max_concurrent', 3)
        self.timeout = self.config.get('execution', {}).get('timeout', 60)
        self.retries = self.config.get('execution', {}).get('retries', 1)
        
        # Load prompts
        from Core.aot.prompts.atom_execution import ATOM_EXECUTION_TEMPLATE
        self.prompt_template = ATOM_EXECUTION_TEMPLATE
    
    async def execute_atoms(self, dag: AtomDAG, conversation_history: List[Dict[str, str]]) -> Dict[str, AtomResult]:
        """
        Execute all atoms in the DAG according to their dependencies.
        
        Args:
            dag: The AtomDAG containing atoms and their dependencies
            conversation_history: The conversation history for context
            
        Returns:
            Dictionary mapping atom IDs to their execution results
        """
        results = {}
        sem = asyncio.Semaphore(self.max_concurrent)
        
        # Process each execution level in sequence
        for level_idx, level in enumerate(dag.execution_levels):
            logger.info(f"Executing level {level_idx+1} with {len(level)} atoms")
            
            # Create tasks for all atoms in this level
            tasks = []
            for atom_id in level:
                atom = dag.atoms.get(atom_id)
                if not atom:
                    logger.warning(f"Atom {atom_id} not found in DAG")
                    continue
                
                # Get dependencies results
                dependency_results = {}
                for dep_id in atom.inputs:
                    if dep_id in results:
                        dependency_results[dep_id] = results[dep_id]
                    else:
                        logger.warning(f"Dependency {dep_id} for atom {atom_id} not found in results")
                
                # Create execution task
                task = self._execute_atom_with_semaphore(
                    sem, atom, dependency_results, conversation_history
                )
                tasks.append((atom_id, asyncio.create_task(task)))
            
            # Wait for all tasks in this level to complete
            for atom_id, task in tasks:
                try:
                    result = await task
                    results[atom_id] = result
                except Exception as e:
                    logger.error(f"Error executing atom {atom_id}: {e}")
                    # Create a failed result
                    results[atom_id] = AtomResult(
                        atom_id=atom_id,
                        status=AtomStatus.FAILED,
                        content=f"Failed to execute: {str(e)}",
                        error=str(e)
                    )
        
        return results
    
    async def _execute_atom_with_semaphore(
        self, 
        semaphore: asyncio.Semaphore, 
        atom: Atom, 
        dependency_results: Dict[str, AtomResult], 
        conversation_history: List[Dict[str, str]]
    ) -> AtomResult:
        """Execute an atom with concurrency control via semaphore"""
        async with semaphore:
            return await self._execute_atom(atom, dependency_results, conversation_history)
    
    async def _execute_atom(
        self, 
        atom: Atom, 
        dependency_results: Dict[str, AtomResult],
        conversation_history: List[Dict[str, str]]
    ) -> AtomResult:
        """
        Execute a single atom.
        
        Args:
            atom: The atom to execute
            dependency_results: Results from atoms this one depends on
            conversation_history: The conversation history for context
            
        Returns:
            AtomResult containing the execution result
        """
        logger.info(f"Executing atom {atom.id}: {atom.description}")
        
        try:
            # Format the prompt with dependency results
            prompt = self._format_atom_prompt(atom, dependency_results, conversation_history)
            
            # Execute with timeout
            execution_task = self._call_llm_for_atom(prompt, atom)
            content = await asyncio.wait_for(execution_task, timeout=self.timeout)
            
            # Create successful result
            return AtomResult(
                atom_id=atom.id,
                status=AtomStatus.COMPLETED,
                content=content
            )
            
        except asyncio.TimeoutError:
            logger.warning(f"Atom {atom.id} execution timed out after {self.timeout}s")
            return AtomResult(
                atom_id=atom.id,
                status=AtomStatus.TIMEOUT,
                content="Execution timed out",
                error=f"Timeout after {self.timeout}s"
            )
            
        except Exception as e:
            logger.error(f"Error in atom {atom.id} execution: {e}")
            return AtomResult(
                atom_id=atom.id,
                status=AtomStatus.FAILED,
                content=f"Execution failed: {str(e)}",
                error=str(e)
            )
    
    def _format_atom_prompt(
        self, 
        atom: Atom, 
        dependency_results: Dict[str, AtomResult],
        conversation_history: List[Dict[str, str]]
    ) -> str:
        """Format the prompt for atom execution with dependencies"""
        # Extract relevant context
        context = self._extract_context(conversation_history)
        
        # Format dependencies section
        dependencies_text = ""
        for dep_id, result in dependency_results.items():
            if result and result.status == AtomStatus.COMPLETED:
                dependencies_text += f"DEPENDENCY {dep_id}:\n{result.content}\n\n"
        
        if not dependencies_text and atom.inputs:
            dependencies_text = "(No results available from dependencies)"
        
        # Format the final prompt
        return self.prompt_template.format(
            context=context,
            atom_description=atom.description,
            atom_type=atom.type.name,
            atom_query=atom.query,
            dependencies=dependencies_text
        )
    
    def _extract_context(self, conversation_history: List[Dict[str, str]]) -> str:
        """Extract relevant context from conversation history"""
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
    
    async def _call_llm_for_atom(self, prompt: str, atom: Atom) -> str:
        """Call the LLM to execute an atom with retries"""
        attempt = 0
        last_error = None
        
        while attempt <= self.retries:
            try:
                # Create a conversation for this specific atom
                conversation = [
                    {"role": "system", "content": f"You are executing a thought atom of type {atom.type.name}."},
                    {"role": "user", "content": prompt}
                ]
                
                result = await self.llm.generate_response(conversation)
                return result
                
            except Exception as e:
                last_error = e
                attempt += 1
                if attempt <= self.retries:
                    logger.warning(f"Retrying atom {atom.id} after error: {e}")
                    await asyncio.sleep(1)  # Brief delay before retry
        
        # All retries failed
        if last_error:
            raise last_error
        else:
            raise RuntimeError(f"Failed to execute atom {atom.id} after {self.retries} retries")