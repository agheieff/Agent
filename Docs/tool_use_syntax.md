#LLM Tool Use Syntax Documentation

LLM invokes external tools using structured text blocks as follows:

## Tool Invocation (from LLM):

@tool <tool_name>
arg1: value
arg2: |
  multiline
  value
@end

## Tool Result (returned to LLM):

Each result includes an exit code:
- 0 = success (output contains function result).
- Non-zero = error (output contains error message).

```
@result <tool_name>
exit_code: 0
output: |
  successful function output (if any)
@end
```

## Example of failure:

```
@result <tool_name>
exit_code: 1
output: |
  Error message explaining the issue
@end
```