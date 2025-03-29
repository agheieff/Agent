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
    cleaned_tokens = []
    try:
        tokens = tokenize.generate_tokens(io.BytesIO(source.encode('utf-8')).readline)

        for token_info in tokens:
            tok_type = token_info.type
            if tok_type == tokenize.COMMENT:
                continue
            cleaned_tokens.append(token_info)

    except tokenize.TokenError as e:
        logger.error(f"Failed to tokenize source: {e}")
        return source
    except Exception as e:
        logger.error(f"An unexpected error occurred during tokenization: {e}")
        return source

    try:
        cleaned_source = tokenize.untokenize(cleaned_tokens)
    except Exception as e:
        logger.error(f"Failed to untokenize source: {e}")
        return source

    lines = cleaned_source.splitlines()
    non_empty_lines = [line for line in lines if line.strip()]
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
    # Determine the directory containing this script and its parent
    script_dir = Path(__file__).parent.resolve()
    default_target_dir = script_dir.parent

    parser = argparse.ArgumentParser(
        description="Recursively remove comments from Python files in a directory.",
        epilog="WARNING: This script modifies files in-place unless --dry-run is used. Backup your code!"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        # Default to the parent directory of the script
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

    # Exclude the script's own directory if it's within the target directory
    # (though usually it won't be since we start one level up)
    script_dir_relative = None
    try:
        script_dir_relative = script_dir.relative_to(start_dir)
    except ValueError:
        pass # Script directory is not inside start_dir

    for root, dirs, files in os.walk(start_dir):
        current_dir = Path(root)

        # Skip .venv directories
        if ".venv" in current_dir.parts:
            logger.debug(f"Skipping directory: {current_dir} (virtual environment)")
            # Prevent os.walk from descending further into .venv
            dirs[:] = [d for d in dirs if d != ".venv"]
            continue

        # Skip the script's own directory if applicable
        if script_dir_relative and Path(root).resolve() == script_dir.resolve():
             logger.debug(f"Skipping script's own directory: {current_dir}")
             dirs[:] = [] # Don't descend further into script's dir
             continue

        for filename in files:
            if filename.endswith(".py") and Path(root) / filename != Path(__file__).resolve(): # Ensure we don't process the script itself
                processed_count += 1
                filepath = current_dir / filename
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
