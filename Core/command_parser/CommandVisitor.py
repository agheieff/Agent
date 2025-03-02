from typing import List, Tuple, Dict, Any, Optional
from antlr4 import *
from .CommandParser import CommandParser
from .CommandLexer import CommandLexer
import logging
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)

@dataclass
class CommandNode:
    """Represents a node in the command tree"""
    type: str
    content: str
    attributes: Dict[str, str] = None
    description: str = None
    dependencies: List[str] = None
    children: List['CommandNode'] = None
    priority: int = 0

class CommandVisitor(CommandParser.CommandVisitorImpl):
    def __init__(self):
        self.commands = []
        self.current_depth = 0
        self.max_depth = 10  # Prevent infinite recursion
        self.dependency_graph = defaultdict(set)
        
    def visitCommand_sequence(self, ctx: CommandParser.Command_sequenceContext) -> List[CommandNode]:
        """Visit a command sequence and return list of parsed commands"""
        try:
            commands = []
            for child in ctx.command_block():
                if self.current_depth >= self.max_depth:
                    logger.error("Maximum nesting depth exceeded")
                    break
                    
                result = self.visitCommand_block(child)
                if result:
                    commands.append(result)
            return commands
        except Exception as e:
            logger.error(f"Error parsing command sequence: {e}")
            return []

    def visitCommand_block(self, ctx: CommandParser.Command_blockContext) -> Optional[CommandNode]:
        """Visit a command block and handle nested structures"""
        try:
            self.current_depth += 1
            
            if ctx.bash_block():
                node = CommandNode(
                    type='bash',
                    content=self._unescape_content(ctx.bash_block().command_content().getText())
                )
            elif ctx.python_block():
                node = CommandNode(
                    type='python',
                    content=self._unescape_content(ctx.python_block().command_content().getText())
                )
            elif ctx.task_block():
                node = self.visitTask_block(ctx.task_block())
            elif ctx.service_block():
                node = CommandNode(
                    type='service',
                    content=self._unescape_content(ctx.service_block().command_content().getText())
                )
            elif ctx.package_block():
                node = CommandNode(
                    type='package',
                    content=self._unescape_content(ctx.package_block().command_content().getText())
                )
            else:
                node = None
                
            self.current_depth -= 1
            return node
            
        except Exception as e:
            logger.error(f"Error parsing command block: {e}")
            self.current_depth -= 1
            return None

    def visitNested_command_block(self, ctx: CommandParser.Nested_command_blockContext) -> Optional[CommandNode]:
        """Visit a nested command block"""
        try:
            if ctx.command_block():
                return self.visitCommand_block(ctx.command_block())
            elif ctx.command_content():
                return CommandNode(
                    type='command',
                    content=self._unescape_content(ctx.command_content().getText())
                )
            return None
        except Exception as e:
            logger.error(f"Error parsing nested command block: {e}")
            return None

    def visitTask_block(self, ctx: CommandParser.Task_blockContext) -> Optional[CommandNode]:
        """Visit a task block and process nested commands"""
        try:
            # Parse attributes
            attrs = {}
            if ctx.attributes():
                attrs = self.visitAttributes(ctx.attributes())
                
            # Get priority from attributes
            priority = int(attrs.get('priority', '0'))
            
            # Process nested elements
            descriptions = []
            commands = []
            dependencies = []
            
            for i in range(len(ctx.children)):
                child = ctx.children[i]
                if isinstance(child, CommandParser.Description_blockContext):
                    desc = self.visitDescription_block(child)
                    if desc:
                        descriptions.append(desc)
                elif isinstance(child, CommandParser.Nested_command_blockContext):
                    cmd = self.visitNested_command_block(child)
                    if cmd:
                        commands.append(cmd)
                elif isinstance(child, CommandParser.Dependency_blockContext):
                    deps = self.visitDependency_block(child)
                    if deps:
                        dependencies.extend(deps)
                        
            # Create node
            node = CommandNode(
                type='task',
                content='',
                attributes=attrs,
                description='\n'.join(descriptions),
                dependencies=dependencies,
                children=commands,
                priority=priority
            )
            
            # Update dependency graph
            task_id = attrs.get('id')
            if task_id and dependencies:
                for dep in dependencies:
                    self.dependency_graph[task_id].add(dep)
                    
            return node
            
        except Exception as e:
            logger.error(f"Error parsing task block: {e}")
            return None

    def visitAttributes(self, ctx: CommandParser.AttributesContext) -> Dict[str, str]:
        """Visit attributes and return as dictionary"""
        attrs = {}
        for attr in ctx.attribute():
            name = attr.NAME().getText()
            value = attr.STRING().getText().strip('"')
            attrs[name] = value
        return attrs

    def visitDependency_block(self, ctx: CommandParser.Dependency_blockContext) -> List[str]:
        """Visit dependency block and validate dependencies"""
        try:
            deps = []
            dep_list = ctx.dependency_list()
            if dep_list:
                for dep in dep_list.dependency():
                    dep_id = dep.getText()
                    deps.append(dep_id)
                    
                    # Check for cyclic dependencies
                    if self._has_cycle(dep_id):
                        logger.warning(f"Cyclic dependency detected: {dep_id}")
                        
            return deps
        except Exception as e:
            logger.error(f"Error parsing dependency block: {e}")
            return []

    def _has_cycle(self, node: str, visited: set = None, path: set = None) -> bool:
        """Check for cycles in dependency graph using DFS"""
        if visited is None:
            visited = set()
        if path is None:
            path = set()
            
        visited.add(node)
        path.add(node)
        
        for neighbor in self.dependency_graph[node]:
            if neighbor not in visited:
                if self._has_cycle(neighbor, visited, path):
                    return True
            elif neighbor in path:
                return True
                
        path.remove(node)
        return False

    def _unescape_content(self, content: str) -> str:
        """Unescape brackets in command content"""
        return content.replace('\\<', '<').replace('\\>', '>')

    def visitDependency_list(self, ctx: CommandParser.Dependency_listContext) -> List[str]:
        """Visit dependency list and return as list of strings"""
        return [dep.getText() for dep in ctx.dependency()]

    def visitDependency(self, ctx: CommandParser.DependencyContext) -> str:
        """Visit dependency and return as string"""
        return ctx.getText()

    def visitDescription_block(self, ctx: CommandParser.Description_blockContext) -> str:
        """Visit a description block and return its content"""
        # Adjusted to match the grammar tokens properly
        content = ''.join([t.getText() for t in ctx.children])
        return content.strip("<description>").strip("</description>").strip()
