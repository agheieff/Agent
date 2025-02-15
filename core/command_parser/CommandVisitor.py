from typing import List, Tuple, Dict
from antlr4 import *
from .CommandParser import CommandParser
from .CommandLexer import CommandLexer
import logging

logger = logging.getLogger(__name__)

class CommandVisitor(CommandParser.CommandVisitorImpl):
    def __init__(self):
        self.commands = []
        
    def visitCommand_sequence(self, ctx: CommandParser.Command_sequenceContext) -> List[Tuple[str, Dict]]:
        """Visit a command sequence and return list of parsed commands"""
        for child in ctx.children:
            if isinstance(child, CommandParser.Bash_blockContext):
                self.commands.append(('bash', {
                    'content': child.CONTENT().getText().strip()
                }))
            elif isinstance(child, CommandParser.Python_blockContext):
                self.commands.append(('python', {
                    'content': child.CONTENT().getText().strip()
                }))
            elif isinstance(child, CommandParser.Task_blockContext):
                task = self.visitTask_block(child)
                if task:
                    self.commands.append(('task', task))
        return self.commands

    def visitBash_block(self, ctx: CommandParser.Bash_blockContext) -> Dict:
        """Visit a bash block and return its content"""
        return {
            'content': ctx.CONTENT().getText().strip()
        }

    def visitPython_block(self, ctx: CommandParser.Python_blockContext) -> Dict:
        """Visit a python block and return its content"""
        return {
            'content': ctx.CONTENT().getText().strip()
        }

    def visitTask_block(self, ctx: CommandParser.Task_blockContext) -> Dict:
        """Visit a task block and return its structured content"""
        try:
            # Parse attributes
            attrs = {}
            for attr in ctx.attributes().attribute():
                name = attr.NAME().getText()
                value = attr.STRING().getText().strip('"')
                attrs[name] = value
            
            # Parse description and command blocks
            descriptions = []
            commands = []
            
            children = list(ctx.children)
            for i in range(3, len(children)-1):  # Skip task tags
                child = children[i]
                if isinstance(child, CommandParser.Description_blockContext):
                    descriptions.append(child.CONTENT().getText().strip())
                elif isinstance(child, CommandParser.Command_blockContext):
                    commands.append(child.CONTENT().getText().strip())
            
            return {
                'attributes': attrs,
                'descriptions': descriptions,
                'commands': commands
            }
            
        except Exception as e:
            logger.error(f"Error parsing task block: {e}")
            return None

    def visitDescription_block(self, ctx: CommandParser.Description_blockContext) -> str:
        """Visit a description block and return its content"""
        return ctx.CONTENT().getText().strip()

    def visitCommand_block(self, ctx: CommandParser.Command_blockContext) -> str:
        """Visit a command block and return its content"""
        return ctx.CONTENT().getText().strip() 