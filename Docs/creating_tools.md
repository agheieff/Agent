# Creating Tools
## Basic Tool Structure

```python
from Tools.base import Tool, Argument, ArgumentType

class MyTool(Tool):
    def __init__(self):
        super().__init__(
            name="my_tool",
            description="What my tool does",
            args=[
                Argument("param1", ArgumentType.STRING, "Description"),
                Argument("param2", ArgumentType.INT, "Optional param", 
                        optional=True, default=42)
            ]
        )
    
    def _run(self, args):
        # Tool logic here
        return {"result": "success"}  # Or raise exception on failure
```

## Example Tool

```python
from Tools.base import Tool, Argument, ArgumentType

class Calculator(Tool):
    def __init__(self):
        super().__init__(
            name="calculator",
            description="Performs basic math operations",
            args=[
                Argument("a", ArgumentType.FLOAT, "First number"),
                Argument("b", ArgumentType.FLOAT, "Second number"),
                Argument("op", ArgumentType.STRING, "Operation (add/sub/mul/div)")
            ]
        )
    
    def _run(self, args):
        a, b, op = args["a"], args["b"], args["op"]
        
        if op == "add": return {"result": a + b}
        if op == "sub": return {"result": a - b}
        if op == "mul": return {"result": a * b}
        if op == "div": return {"result": a / b}
        
        raise ValueError(f"Unknown operation: {op}")
```

## Best Practices
- Keep tools focused on single operations
- Use clear, descriptive argument names
- Return structured data (dicts) from _run()
- Raise exceptions for error condition
