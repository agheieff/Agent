from typing import List, Tuple, Dict, Any, Optional
from antlr4 import *
from .CommandParser import CommandParser
from .CommandLexer import CommandLexer
import logging

logger = logging.getLogger(__name__)

class CommandVisitor(CommandParser.CommandVisitorImpl):
    def __init__(self):
        self.commands = []
        
    def visitCommand_sequence(self, ctx: CommandParser.Command_sequenceContext) -> List[Dict]:
        """Visit a command sequence and return list of parsed commands"""
        commands = []
        for child in ctx.children:
            if hasattr(child, 'accept'):
                result = child.accept(self)
                if result:
                    commands.append(result)
        return commands

    def visitBash_block(self, ctx: CommandParser.Bash_blockContext) -> Dict:
        """Visit a bash block and return its content"""
        return {
            'type': 'bash',
            'content': ctx.CONTENT().getText().strip()
        }

    def visitPython_block(self, ctx: CommandParser.Python_blockContext) -> Dict:
        """Visit a python block and return its content"""
        return {
            'type': 'python',
            'content': ctx.CONTENT().getText().strip()
        }

    def visitTask_block(self, ctx: CommandParser.Task_blockContext) -> Dict:
        """Visit a task block and return its structured content"""
        try:
            # Parse attributes
            attrs = {}
            if ctx.attributes():
                attrs = self.visitAttributes(ctx.attributes())

            # Parse descriptions and commands
            descriptions = []
            commands = []
            dependencies = []

            for i in range(len(ctx.children)):
                child = ctx.children[i]
                if hasattr(child, 'accept'):
                    if isinstance(child, CommandParser.Description_blockContext):
                        descriptions.append(
                            child.CONTENT().getText().strip()
                        )
                    elif isinstance(child, CommandParser.Command_blockContext):
                        commands.append(
                            child.CONTENT().getText().strip()
                        )
                    elif isinstance(child, CommandParser.Dependency_blockContext):
                        deps = self.visitDependency_block(child)
                        if deps:
                            dependencies.extend(deps)

            return {
                'type': 'task',
                'attributes': attrs,
                'descriptions': descriptions,
                'commands': commands,
                'dependencies': dependencies
            }
            
        except Exception as e:
            logger.error(f"Error parsing task block: {e}")
            return None

    def visitAttributes(self, ctx) -> Dict:
        """Visit a parse tree produced by CommandParser.attributes."""
        attrs = {}
        for attr in ctx.attribute():
            name = attr.NAME().getText()
            value = attr.STRING().getText().strip('"')
            attrs[name] = value
        return attrs

    def visitDependency_block(self, ctx: CommandParser.Dependency_blockContext) -> List[str]:
        """Visit a parse tree produced by CommandParser.dependency_block."""
        try:
            deps = []
            dep_list = ctx.dependency_list()
            if dep_list:
                for dep in dep_list.dependency():
                    if dep.ID_REF():
                        deps.append(dep.ID_REF().getText())
                    elif dep.TASK_REF():
                        deps.append(dep.TASK_REF().getText())
            return deps
        except Exception as e:
            logger.error(f"Error parsing dependency block: {e}")
            return []

    def visitDependency_list(self, ctx: CommandParser.Dependency_listContext) -> List[str]:
        """Visit a parse tree produced by CommandParser.dependency_list."""
        return [dep.getText() for dep in ctx.dependency()]

    def visitDependency(self, ctx: CommandParser.DependencyContext) -> str:
        """Visit a parse tree produced by CommandParser.dependency."""
        if ctx.ID_REF():
            return ctx.ID_REF().getText()
        return ctx.TASK_REF().getText()

    def visitDescription_block(self, ctx: CommandParser.Description_blockContext) -> str:
        """Visit a description block and return its content"""
        return ctx.CONTENT().getText().strip()

    def visitCommand_block(self, ctx: CommandParser.Command_blockContext) -> str:
        """Visit a command block and return its content"""
        return ctx.CONTENT().getText().strip() 