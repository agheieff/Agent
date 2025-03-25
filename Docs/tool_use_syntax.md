# Tool Use Syntax
## Calling Tools (LLM → Agent)

```
@tool <tool_name>
arg1: value1
arg2: value2
@end
```

## Multi-line arguments:
```
@tool write_file
path: script.py
content: <<<
def hello():
print("Hello world")
if True:
print("Indented properly")
>>>
mode: overwrite
@end
```

###  Key Features:
1. `<<<` starts a multi-line block
2. `>>>` ends it (must be at start of line)
3. Content between keeps its original indentation

4. Next argument can appear immediately after `>>>`

## Tool Results (Agent → LLM)
### Success Case
```
@result <tool_name>
exit_code: 0
output: |
The operation succeeded
with this output
@end
```


### Error Case
```
@result <tool_name>
exit_code: 1
output: Error description
@end
```

## Example Flow

1. Agent decides to use a tool:
```
@tool calculator
a: 5
b: 3
op: add
@end
```


2. System executes and responds:
```
@result calculator
exit_code: 0
output: 8
@end
```
