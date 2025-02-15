from typing import List, Tuple, Dict
from antlr4 import *
from .CommandParser import CommandParser
from .CommandLexer import CommandLexer

class CommandVisitor(CommandParser.CommandVisitorImpl):
    def __init__(self):
        self.commands = []
        
    def visitCommand_sequence(self, ctx: CommandParser.Command_sequenceContext) -> List[Tuple[str, str]]:
        for child in ctx.children:
            if isinstance(child, CommandParser.Bash_blockContext):
                self.commands.append(('bash', child.CONTENT().getText().strip()))
            elif isinstance(child, CommandParser.Python_blockContext):
                self.commands.append(('python', child.CONTENT().getText().strip()))
            elif isinstance(child, CommandParser.Task_blockContext):
                attrs = {}
                for attr in child.attributes().attribute():
                    name = attr.NAME().getText()
                    value = attr.STRING().getText().strip('"')
                    attrs[name] = value
                self.commands.append(('task', {
                    'content': child.CONTENT().getText().strip(),
                    'attributes': attrs
                }))
        return self.commands

    def visitBash_block(self, ctx: CommandParser.Bash_blockContext):
        return ('bash', ctx.CONTENT().getText().strip())

    def visitPython_block(self, ctx: CommandParser.Python_blockContext):
        return ('python', ctx.CONTENT().getText().strip())

    def visitTask_block(self, ctx: CommandParser.Task_blockContext):
        attrs = {}
        for attr in ctx.attributes().attribute():
            name = attr.NAME().getText()
            value = attr.STRING().getText().strip('"')
            attrs[name] = value
        return ('task', {
            'content': ctx.CONTENT().getText().strip(),
            'attributes': attrs
        }) 