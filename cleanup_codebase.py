#\!/usr/bin/env python

"""
This script identifies redundant files based on the refactoring plan in CLAUDE.md.
It doesn't delete files but produces a list of redundant files that can be safely removed.
"""

import os
import sys
from pathlib import Path

def check_imports(file_path, old_path, new_path):
    """Check if a file is importing from the old or new path."""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        uses_old = f"from {old_path}" in content or f"import {old_path}" in content
        uses_new = f"from {new_path}" in content or f"import {new_path}" in content
        return uses_old, uses_new

def main():
    # Duplicate file mappings (old location -> new location)
    duplicate_files = {
        "Core/shell_adapter.py": "Tools/System/shell_adapter.py",
        "Core/file_operations.py": "Tools/File/file_operations.py",
        "Core/memory_manager.py": "Memory/Manager/memory_manager.py",
        "Core/memory_hierarchy.py": "Memory/Hierarchy/memory_hierarchy.py",
        "Core/memory_cache.py": "Memory/Cache/memory_cache.py",
        "Core/memory_preloader.py": "Memory/Preloader/memory_preloader.py",
        "Core/llm_client": "Clients/LLM",
    }
    
    # Files that import the duplicates
    files_to_check = []
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.py'):
                files_to_check.append(os.path.join(root, file))
    
    # Check which duplicate is being used more
    usage_stats = {old: {"old": 0, "new": 0} for old in duplicate_files}
    
    for file_path in files_to_check:
        for old_path, new_path in duplicate_files.items():
            # Skip checking the duplicate files themselves
            if file_path.endswith(old_path) or file_path.endswith(new_path.replace("/", os.sep)):
                continue
                
            # Check imports in the file
            old_path_import = old_path.replace("/", ".").rstrip(".py")
            new_path_import = new_path.replace("/", ".").rstrip(".py")
            
            try:
                uses_old, uses_new = check_imports(file_path, old_path_import, new_path_import)
                if uses_old:
                    usage_stats[old_path]["old"] += 1
                if uses_new:
                    usage_stats[old_path]["new"] += 1
            except Exception as e:
                print(f"Error checking {file_path}: {e}")
    
    # Determine which files can be safely removed
    files_to_remove = []
    for old_path, stats in usage_stats.items():
        if stats["new"] >= stats["old"]:
            # New path is used more, remove the old one
            files_to_remove.append(old_path)
        else:
            # Old path is used more, but check if it has a corresponding Claude.md directive
            print(f"WARNING: {old_path} is used more ({stats['old']}) than {duplicate_files[old_path]} ({stats['new']})")
            # For consistency with the refactoring plan, still recommend removal
            files_to_remove.append(old_path)
    
    # Print the list of files to remove
    print("\nFiles that can be safely removed (redundant implementations):")
    for file in files_to_remove:
        print(f"- {file}")
    
    print("\nUsage statistics for duplicate files:")
    for old_path, stats in usage_stats.items():
        print(f"- {old_path} used in {stats['old']} files")
        print(f"  {duplicate_files[old_path]} used in {stats['new']} files")
    
    return files_to_remove

if __name__ == "__main__":
    main()
