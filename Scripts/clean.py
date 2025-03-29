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
    tokens_for_body = []
    preserved_shebang_string = None
    first_token_processed = False

    try:
        source_bytes = source.encode('utf-8')
        byte_stream = io.BytesIO(source_bytes)
        tokens = tokenize.tokenize(byte_stream.readline)

        for token_info in tokens:
            tok_type = token_info.type
            tok_string = token_info.string

            if not first_token_processed:
                first_token_processed = True
                if tok_type == tokenize.COMMENT and tok_string.startswith('#!'):
                    preserved_shebang_string = tok_string # Store the string directly
                    logger.debug("Preserving shebang.")
                    continue
                elif tok_type == tokenize.ENCODING:
                    logger.debug("Skipping encoding token.")
                    continue

            if tok_type == tokenize.COMMENT or tok_type == tokenize.ENCODING:
                continue

            tokens_for_body.append(token_info)

    except tokenize.TokenError as e:
        logger.error(f"TokenError during tokenization: {e}")
        return source
    except Exception as e:
        logger.error(f"An unexpected error occurred during tokenization: {e}", exc_info=True)
        return source

    try:
        # Untokenize only the body tokens
        cleaned_body = tokenize.untokenize(tokens_for_body)
        if isinstance(cleaned_body, bytes):
            cleaned_body = cleaned_body.decode('utf-8')

        # Clean empty lines from the body *only*
        body_lines = cleaned_body.splitlines()
        non_empty_body_lines = [line for line in body_lines if line.strip()]
        cleaned_body_no_empty = "\n".join(non_empty_body_lines)

        # Reconstruct final source
        final_parts = []
        if preserved_shebang_string:
            final_parts.append(preserved_shebang_string)

        # Add cleaned body only if it's not empty
        if cleaned_body_no_empty:
             final_parts.append(cleaned_body_no_empty)

        # Join parts with newline, add trailing newline if content exists
        if final_parts:
            final_source = "\n".join(final_parts) + "\n"
        else:
             # Handle case where original source might have only contained comments/whitespace
             # or was empty to begin with
             if source.strip(): # Original had non-whitespace content (likely just comments/shebang)
                 final_source = "\n" # Return single newline if original wasn't truly empty
             else:
                 final_source = "" # Return empty if original was empty/whitespace only


    except Exception as e:
        logger.error(f"Failed to untokenize or reconstruct source: {e}")
        return source

    return final_source


def process_file(filepath: Path, dry_run: bool = False) -> bool:
    logger.debug(f"Processing file: {filepath}")
    changed = False
    try:
        original_content = filepath.read_text(encoding='utf-8')
        cleaned_content = remove_comments_and_excess_whitespace(original_content)

        # Normalize line endings in original content for comparison if needed
        # original_content_normalized = "\n".join(original_content.splitlines()) + ("\n" if original_content.endswith(('\n', '\r\n')) else "")

        # Compare, accounting for potential trailing newline differences if necessary
        # For simplicity, let's compare directly first
        if original_content != cleaned_content:
            # Optional: More robust check ignoring only trailing whitespace differences
            # if original_content.rstrip() != cleaned_content.rstrip():
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
            # else:
            #     logger.debug(f"Content differs only by trailing whitespace/newlines: {filepath}")
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

        # Check if script_dir is a subdirectory of start_dir before checking equality
        # This avoids errors if start_dir is higher up the tree than script_dir's parent
        try:
             is_relative = script_dir.relative_to(start_dir)
             # Only skip if current_dir *is* script_dir
             if current_dir == script_dir:
                 logger.debug(f"Skipping script's own directory: {current_dir}")
                 dirs[:] = []
                 continue
        except ValueError:
             # script_dir is not under start_dir, no need to skip based on this check
             pass


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
