#!/usr/bin/env python3
import os
import subprocess
import tokenize
import io

def remove_comments_and_docstrings(source):
    """
    Remove comments and unassigned triple-quoted strings (docstring-like comments)
    from the source code, and record the line numbers occupied by the removed docstrings.
    
    This function uses an indent-tracking heuristic:
      - All COMMENT tokens are removed.
      - A STRING token is removed if it starts with triple quotes and:
          * It appears right after a NEWLINE or INDENT, and
          * Its starting column equals the current indent level.
    Returns a tuple: (new_source, removed_lines)
      new_source: the untokenized source code (which may still contain leftover blank lines)
      removed_lines: a set of line numbers (1-indexed) that were occupied by removed docstrings.
    """
    io_obj = io.StringIO(source)
    output_tokens = []
    removed_lines = set()
    
    indent_stack = [0]  # module-level indentation is 0
    prev_toktype = None
    
    try:
        tokens = list(tokenize.generate_tokens(io_obj.readline))
    except Exception as e:
        print(f"Tokenization error: {e}")
        return source, removed_lines

    for tok in tokens:
        token_type, token_string, (sline, scol), (eline, ecol), line = tok

        if token_type == tokenize.INDENT:
            indent_stack.append(len(token_string))
            output_tokens.append(tok)
            prev_toktype = token_type
            continue

        if token_type == tokenize.DEDENT:
            if len(indent_stack) > 1:
                indent_stack.pop()
            output_tokens.append(tok)
            prev_toktype = token_type
            continue

        if token_type == tokenize.COMMENT:
            continue

        if token_type == tokenize.STRING:
            # Check if the string is triple-quoted.
            if token_string.startswith('"""') or token_string.startswith("'''"):
                # If the preceding token is NEWLINE or INDENT and the string starts at the current indent level,
                # assume it's an unassigned docstring. Record its span and skip this token.
                if prev_toktype in (tokenize.NEWLINE, tokenize.INDENT) and scol == indent_stack[-1]:
                    removed_lines.update(range(sline, eline + 1))
                    continue

        output_tokens.append(tok)
        prev_toktype = token_type

    try:
        new_source = tokenize.untokenize(output_tokens)
    except Exception as e:
        print(f"Untokenize error: {e}")
        return source, removed_lines

    return new_source, removed_lines

def remove_comments_from_file(filepath):
    """
    Reads a Python file, removes comments and unassigned docstrings,
    and removes the lines that were solely occupied by a removed triple-quoted docstring.
    Also ensures that lines that are otherwise empty (or contain only stray backslashes)
    are replaced with empty lines, preserving other newline breaks.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()

    # Remove comments and docstrings; get the new source and the set of removed line numbers.
    new_source, removed_lines = remove_comments_and_docstrings(source)
    
    # Split the untokenized source into lines.
    lines = new_source.splitlines()
    final_lines = []
    for i, line in enumerate(lines, start=1):
        # If this line was part of a removed docstring, skip it.
        if i in removed_lines:
            continue
        # If a line contains only whitespace or stray backslashes, clean it to an empty line.
        if line.strip() == "" or all(c == '\\' for c in line.strip()):
            final_lines.append("")
        else:
            final_lines.append(line)
    return "\n".join(final_lines) + "\n"

def main():
    try:
        # List files tracked by git (respects .gitignore).
        result = subprocess.check_output(["git", "ls-files"], universal_newlines=True)
    except subprocess.CalledProcessError:
        print("Error: This does not appear to be a git repository or the git command failed.")
        return

    files = result.splitlines()
    py_files = [f for f in files if f.endswith('.py')]

    if not py_files:
        print("No Python files found in the tracked files.")
        return

    for filepath in py_files:
        print(f"Modifying file: {filepath}")
        try:
            new_code = remove_comments_from_file(filepath)
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
            continue

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_code)
        print(f"Processed: {filepath}")

if __name__ == '__main__':
    main()
