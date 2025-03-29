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
    Removes Python comments using tokenize.tokenize and cleans up blank lines.

    Args:
        source: The source code as a string.

    Returns:
        The source code without comments, or the original source on error.
    """
    cleaned_tokens = []
    try:
        source_bytes = source.encode('utf-8')
        byte_stream = io.BytesIO(source_bytes)
        # Use tokenize.tokenize which reads bytes directly
        tokens = tokenize.tokenize(byte_stream.readline)

        for token_info in tokens:
            tok_type = token_info.type

            # Skip comments AND the encoding cookie often added by tokenize.tokenize
            if tok_type == tokenize.COMMENT or tok_type == tokenize.ENCODING:
                continue

            cleaned_tokens.append(token_info)

    except tokenize.TokenError as e:
        # This might catch issues like unterminated strings within the source
        logger.error(f"TokenError during tokenization: {e}")
        return source # Return original source on tokenization error
    except Exception as e:
        # Log the actual exception which might be more helpful
        logger.error(f"An unexpected error occurred during tokenization: {e}", exc_info=True)
        return source

    try:
        # Reconstruct the source code from the non-comment tokens
        # untokenize expects token type and string; it should return a string.
        cleaned_source = tokenize.untokenize(cleaned_tokens)
        # Just in case untokenize returns bytes (less common now, but for safety)
        if isinstance(cleaned_source, bytes):
            cleaned_source = cleaned_source.decode('utf-8')

    except Exception as e:
        logger.error(f"Failed to untokenize source: {e}")
        return source # Return original on untokenize error

    # Cleanup of potentially fully empty lines resulted from comment removal
    lines = cleaned_source.splitlines()
    # Keep lines that contain *something* other than whitespace
    non_empty_lines = [line for line in lines if line.strip()]

    # Handle edge cases where the file becomes empty or was empty
    if not non_empty_lines and lines: # Original file wasn't empty but now is
         return "\n" # Return a single newline for non-empty original files that become empty
    elif not non_empty_lines and not lines: # Original file was empty
        return "" # Return empty string for empty original files
    else:
        # Join remaining lines and add a single trailing newline
        return "\n".join(non_empty_lines) + "\n"


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
    script_path = Path(__file__).resolve() # Get absolute path of the script

    for root, dirs, files in os.walk(start_dir):
        current_dir = Path(root)

        # Prevent descending into .venv
        if ".venv" in dirs:
            dirs.remove(".venv")
            logger.debug(f"Skipping descent into: {current_dir / '.venv'}")

        # Prevent descending into the script's own directory if it's under start_dir
        # This check is more relevant if the script is placed within the target structure
        if script_dir.is_relative_to(start_dir) and current_dir == script_dir:
            logger.debug(f"Skipping script's own directory: {current_dir}")
            dirs[:] = [] # Clear dirs for this path so os.walk doesn't proceed
            continue

        for filename in files:
            if filename.endswith(".py"):
                filepath = current_dir / filename
                # Explicitly skip processing the script itself
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
