#!/usr/bin/env python

"""
Unit tests for the TaskManager class
"""

import sys
import os
from pathlib import Path
import shutil
import json

# Add parent directory to path to allow imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from Core.task_manager import TaskManager

# Create a temporary directory for testing
TEST_DIR = Path(__file__).parent.parent / "temp" / "tasks"

def setup_fresh():
    """Set up a fresh test environment"""
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    return TaskManager(TEST_DIR)

def setup():
    """Set up the test environment without clearing previous data"""
    if not TEST_DIR.exists():
        TEST_DIR.mkdir(parents=True, exist_ok=True)
    return TaskManager(TEST_DIR)

def test_basic_task_creation():
    """Test basic task creation and retrieval"""
    print("\n=== Testing Basic Task Creation ===")
    
    task_mgr = setup_fresh()  # Start with a clean environment
    
    # Create a task
    task_id = task_mgr.add_task(
        title="Test Task",
        description="This is a test task",
        priority=TaskManager.PRIORITY_HIGH,
        tags=["test", "demo"]
    )
    
    # Retrieve the task
    task = task_mgr.get_task(task_id)
    
    # Check if fields are correct
    assert task is not None, "Task should exist"
    assert task.get('title') == "Test Task", f"Title is {task.get('title')}, expected 'Test Task'"
    assert task.get('priority') == TaskManager.PRIORITY_HIGH, f"Priority is {task.get('priority')}, expected {TaskManager.PRIORITY_HIGH}"
    assert task.get('progress') == 0, f"Progress should start at 0, got {task.get('progress')}"
    
    print("✅ Basic task creation passed")
    return task_id

def test_task_updates(task_id):
    """Test task updates including progress and status"""
    print("\n=== Testing Task Updates ===")
    
    task_mgr = setup()
    
    # Update task progress
    task_mgr.update_task_progress(task_id, 50, "Halfway done")
    task = task_mgr.get_task(task_id)
    assert task.get('progress') == 50, f"Progress should be 50, got {task.get('progress')}"
    
    # Update task status
    task_mgr.update_task_status(task_id, "in_progress", "Starting work")
    task = task_mgr.get_task(task_id)
    assert task.get('status') == "in_progress", f"Status should be 'in_progress', got {task.get('status')}"
    
    # Check history entries
    assert len(task.get('history', [])) >= 2, f"Should have at least 2 history entries, got {len(task.get('history', []))}"
    
    print("✅ Task updates passed")

def test_task_search_and_filter():
    """Test task search and filtering capabilities"""
    print("\n=== Testing Task Search and Filtering ===")
    
    # Start with a fresh environment for these tests
    task_mgr = setup_fresh()
    
    # Create various tasks
    task_mgr.add_task(title="Search Test 1", description="Find me", tags=["search"])
    task_mgr.add_task(title="Search Test 2", description="Also find me", tags=["search", "important"])
    task_mgr.add_task(title="Different", description="This has search term", tags=["other"])
    task_mgr.add_task(title="High Priority", description="Important", priority=TaskManager.PRIORITY_HIGH, tags=["important"])
    
    # Test search
    results = task_mgr.search_tasks("find")
    assert len(results) == 2, f"Should find 2 tasks with 'find', got {len(results)}"
    
    # Test search with different term
    results = task_mgr.search_tasks("search")
    assert len(results) == 3, f"Should find 3 tasks with 'search', got {len(results)}"
    
    # Test getting by tag
    results = task_mgr.get_tasks_by_tag("important")
    assert len(results) == 2, f"Should find 2 tasks with 'important' tag, got {len(results)}"
    
    # Test getting by status - all tasks should be pending
    results = task_mgr.get_tasks_by_status("pending")
    assert len(results) == 4, f"Should find 4 pending tasks, got {len(results)}"
    
    # Test getting active tasks sorted by priority
    results = task_mgr.get_active_tasks(sort_by_priority=True)
    assert results[0].get('priority') == TaskManager.PRIORITY_HIGH, "First task should be highest priority"
    
    print("✅ Task search and filtering passed")

def main():
    """Run all tests with proper setup and cleanup"""
    print("=== TaskManager Tests ===")
    
    try:
        # Set up a clean environment
        if TEST_DIR.exists():
            shutil.rmtree(TEST_DIR)
        TEST_DIR.mkdir(parents=True, exist_ok=True)
        
        # Run tests in sequence
        task_id = test_basic_task_creation()
        test_task_updates(task_id)
        test_task_search_and_filter()
        
        print("\n✅ All tests completed successfully")
        return True
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return False
    finally:
        # Clean up
        if TEST_DIR.exists():
            shutil.rmtree(TEST_DIR)

if __name__ == "__main__":
    result = main()
    sys.exit(0 if result else 1)