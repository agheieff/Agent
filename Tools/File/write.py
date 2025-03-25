import os
from Tools.base import Tool, Argument, ArgumentType

class WriteFile(Tool):
    def __init__(self):
        super().__init__(
            name="write_file",
            description="Writes content to a file",
            args=[
                Argument("path", ArgumentType.FILEPATH, "File path"),
                Argument("content", ArgumentType.STRING, "Content to write"),
                Argument("overwrite", ArgumentType.BOOLEAN, 
                        "Overwrite if exists", optional=True, default=False)
            ]
        )

    def _run(self, args):
        if os.path.exists(args["path"]) and not args["overwrite"]:
            return {"exists": True, "path": args["path"]}
            
        os.makedirs(os.path.dirname(args["path"]), exist_ok=True)
        
        with open(args["path"], 'w') as f:
            f.write(args["content"])
            
        return {"success": True, "path": args["path"], "bytes": len(args["content"])}
