#!/usr/bin/env python3
import os
import tokenize
import io
import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def remove_comments_and_excess_whitespace(source: str) -> str:
    """
    Removes Python comments using tokenize.tokenize, preserves shebang,
    and cleans up blank lines.

    Args:
        source: The source code as a string.

    Returns:
        The source code without comments, or the original source on error.
    """
    cleaned_tokens_for_untokenize = []
    preserved_shebang_token = None
    first_token_processed = False

    try:
        source_bytes = source.encode('utf-8')
        byte_stream = io.BytesIO(source_bytes)
        tokens = tokenize.tokenize(byte_stream.readline)

        for token_info in tokens:
            tok_type = token_info.type
            tok_string = token_info.string

            # --- Shebang and Encoding Handling (First Token) ---
            if not first_token_processed:
                first_token_processed = True
                # Check if the first token is a comment starting with #!
                if tok_type == tokenize.COMMENT and tok_string.startswith('#!'):
                    preserved_shebang_token = token_info
                    logger.debug("Preserving shebang.")
                    continue # Skip adding shebang to list for untokenize initially
                # Skip encoding cookie if it's the first token
                elif tok_type == tokenize.ENCODING:
                    logger.debug("Skipping encoding token.")
                    continue
                # If the first token isn't shebang or encoding, fall through to process normally

            # --- Regular Comment/Encoding Skipping (After First Token) ---
            if tok_type == tokenize.COMMENT:
                continue # Skip regular comments
            # Encoding shouldn't appear after first token, but skip just in case
            if tok_type == tokenize.ENCODING:
                continue

            # Add all other valid tokens to the list for untokenize
            cleaned_tokens_for_untokenize.append(token_info)

    except tokenize.TokenError as e:
        logger.error(f"TokenError during tokenization: {e}")
        return source
    except Exception as e:
        logger.error(f"An unexpected error occurred during tokenization: {e}", exc_info=True)
        return source

    try:
        # Reconstruct the source code *without* the shebang for now
        cleaned_source_body = tokenize.untokenize(cleaned_tokens_for_untokenize)
        if isinstance(cleaned_source_body, bytes):
            cleaned_source_body = cleaned_source_body.decode('utf-8')

        # --- Prepend Shebang if it was preserved ---
        final_source_parts = []
        if preserved_shebang_token:
            final_source_parts.append(preserved_shebang_token.string) # Add shebang line

        # Add the rest of the cleaned code
        final_source_parts.append(cleaned_source_body)
        cleaned_source = "\n".join(final_source_parts)

    except Exception as e:
        logger.error(f"Failed to untokenize source: {e}")
        return source

    # Cleanup potentially fully empty lines resulted from comment removal
    lines = cleaned_source.splitlines()
    # Preserve the first line (shebang) if it exists, then filter rest
    first_line = lines[0] if lines and preserved_shebang_token else None
    non_empty_lines = [line for line in lines[(1 if first_line else 0):] if line.strip()]

    # Reconstruct final output
    output_lines = []
    if first_line:
        output_lines.append(first_line)
    output_lines.extend(non_empty_lines)

    # Handle edge cases for empty files
    if not output_lines and lines: # Original file wasn't empty but now is (except shebang)
        return (first_line + "\n") if first_line else "\n"
    elif not output_lines and not lines: # Original file was empty
        return ""
    else:
        # Join remaining lines and add a single trailing newline
        return "\n".join(output_lines) + "\n"


def process_file(filepath: Path, dry_run: bool = False) -> bool:
    logger.debug(f"Processing file: {filepath}")
    changed = False
    try:
        original_content = filepath.read_text(encoding='utf-8')
        cleaned_content = remove_comments_and_excess_whitespace(original_content)

        if original_content != cleaned_content:
            changed = True
            if dry_run:
                logger.info(f"[DRY RUN] Would modify: {filepath}")
            else:
                try:
                    filepath.write_text(cleaned_content, encoding='utf-8')
                    logger.info(f"Modified: {filepath}")
                except OSError as e:
                    logger.error(f"Failed to write changes to {filepath}: {e}")
                    changed = False
        else:
            logger.debug(f"No changes needed for: {filepath}")

    except tokenize.TokenError as e:
        logger.warning(f"Skipping file due to tokenization error: {filepath} - {e}")
    except UnicodeDecodeError as e:
        logger.warning(f"Skipping file due to encoding error (not UTF-8?): {filepath} - {e}")
    except OSError as e:
        logger.error(f"Cannot read file {filepath}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error processing file {filepath}: {e}", exc_info=True)

    return changed


def main():
    script_dir = Path(__file__).parent.resolve()
    default_target_dir = script_dir.parent

    parser = argparse.ArgumentParser(
        description="Recursively remove comments from Python files in a directory.",
        epilog="WARNING: This script modifies files in-place unless --dry-run is used. Backup your code!"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=str(default_target_dir),
        help=f"The root directory to scan for .py files (default: parent directory '{default_target_dir}')"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan files and report changes without actually modifying them."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging."
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    start_dir = Path(args.directory).resolve()
    if not start_dir.is_dir():
        logger.critical(f"Error: Directory not found or invalid: {start_dir}")
        return

    mode = "Dry run" if args.dry_run else "Modify"
    logger.info(f"--- Starting Comment Removal ({mode}) ---")
    logger.info(f"Target Directory: {start_dir}")

    modified_count = 0
    processed_count = 0
    script_path = Path(__file__).resolve()

    for root, dirs, files in os.walk(start_dir):
        current_dir = Path(root)

        if ".venv" in dirs:
            dirs.remove(".venv")
            logger.debug(f"Skipping descent into: {current_dir / '.venv'}")

        if script_dir.is_relative_to(start_dir) and current_dir == script_dir:
             logger.debug(f"Skipping script's own directory: {current_dir}")
             dirs[:] = []
             continue

        for filename in files:
            if filename.endswith(".py"):
                filepath = current_dir / filename
                if filepath.resolve() == script_path:
                    logger.debug(f"Skipping self: {filepath}")
                    continue

                processed_count += 1
                if process_file(filepath, args.dry_run):
                    modified_count += 1

    logger.info("--- Scan Complete ---")
    logger.info(f"Processed {processed_count} Python files.")
    if args.dry_run:
        logger.info(f"Files that *would* be modified: {modified_count}")
    else:
        logger.info(f"Files modified: {modified_count}")


if __name__ == "__main__":
    main()
