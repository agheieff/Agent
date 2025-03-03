#!/usr/bin/env python

"""
Test runner for all unit and integration tests
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path

def run_test(test_path, verbose=False):
    """Run a single test file and return success status"""
    print(f"Running test: {test_path}")
    
    cmd = [sys.executable, test_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if verbose or result.returncode != 0:
        print(result.stdout)
        if result.stderr:
            print(f"STDERR: {result.stderr}")
    
    if result.returncode == 0:
        print(f"✅ {test_path.name} - PASSED")
        return True
    else:
        print(f"❌ {test_path.name} - FAILED (exit code {result.returncode})")
        return False

def discover_tests(test_dir=None, pattern="test_*.py"):
    """Discover all test files matching the pattern"""
    if test_dir is None:
        test_dir = Path(__file__).parent
    
    test_files = []
    for file in test_dir.glob(f"**/{pattern}"):
        if file.is_file():
            test_files.append(file)
    
    return sorted(test_files)

def main():
    """Main test runner entry point"""
    parser = argparse.ArgumentParser(description="Run agent tests")
    parser.add_argument("--unit", action="store_true", help="Run only unit tests")
    parser.add_argument("--integration", action="store_true", help="Run only integration tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show output from all tests")
    parser.add_argument("tests", nargs="*", help="Specific test files to run")
    args = parser.parse_args()
    
    test_dir = Path(__file__).parent
    unit_dir = test_dir / "unit"
    integration_dir = test_dir / "integration"
    
    # Discover tests based on arguments
    if args.tests:
        # Run specific tests
        test_files = []
        for test_name in args.tests:
            # Handle both relative and absolute paths
            test_path = Path(test_name)
            if not test_path.is_absolute():
                # Try to find in unit/ or integration/
                for search_dir in [unit_dir, integration_dir]:
                    potential_path = search_dir / test_path
                    if potential_path.exists():
                        test_files.append(potential_path)
                        break
                    # Try with .py extension added
                    if not test_path.suffix:
                        potential_path = search_dir / (test_path.name + ".py")
                        if potential_path.exists():
                            test_files.append(potential_path)
                            break
            else:
                # Absolute path provided
                if test_path.exists():
                    test_files.append(test_path)
    else:
        # Auto-discover tests
        test_files = []
        if not args.integration:  # Run unit tests by default or if --unit specified
            unit_tests = discover_tests(unit_dir)
            test_files.extend(unit_tests)
            print(f"Discovered {len(unit_tests)} unit tests")
        
        if not args.unit:  # Run integration tests by default or if --integration specified
            integration_tests = discover_tests(integration_dir)
            test_files.extend(integration_tests)
            print(f"Discovered {len(integration_tests)} integration tests")
    
    if not test_files:
        print("No test files found!")
        return 1
    
    # Create temp dir for test artifacts
    temp_dir = test_dir / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    # Run tests
    print(f"Running {len(test_files)} tests...")
    passed = 0
    failed = 0
    
    for test_file in test_files:
        if run_test(test_file, args.verbose):
            passed += 1
        else:
            failed += 1
    
    # Print summary
    print("\n=== Test Summary ===")
    print(f"Total tests: {passed + failed}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    return 1 if failed > 0 else 0

if __name__ == "__main__":
    sys.exit(main())