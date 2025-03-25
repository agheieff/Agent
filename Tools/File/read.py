import os
from Tools.base import Tool, Argument, ArgumentType

class ReadFile(Tool):
    def __init__(self):
        super().__init__(
            name="read_file",
            description="Reads contents of a file",
            args=[
                Argument("path", ArgumentType.FILEPATH, "Path to file"),
                Argument("lines", ArgumentType.INT, "Lines to read", optional=True, default=100)
            ]
        )

    def _run(self, args):
        with open(args["path"], 'r') as f:
            return ''.join(f.readlines()[:args["lines"]])
