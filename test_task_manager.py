#\!/usr/bin/env python

"""
Test script for the enhanced TaskManager
"""

import asyncio
import sys
import os
from pathlib import Path
import shutil
import json
import time

# Add parent directory to path to allow imports
sys.path.append(str(Path(__file__).parent))

from Core.task_manager import TaskManager

# Create a temporary directory for testing
TEST_DIR = Path(__file__).parent / "test_tasks_temp"

def setup_fresh():
    """Set up a fresh test environment"""
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    TEST_DIR.mkdir(exist_ok=True)
    return TaskManager(TEST_DIR)

def setup():
    """Set up the test environment without clearing previous data"""
    if not TEST_DIR.exists():
        TEST_DIR.mkdir(exist_ok=True)
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

def test_subtask_creation(parent_id):
    """Test creating subtasks"""
    print("\n=== Testing Subtask Creation ===")
    
    task_mgr = setup()
    
    # Add subtasks
    subtask1_id = task_mgr.add_subtask(
        parent_id=parent_id,
        title="Subtask 1",
        description="First subtask"
    )
    
    subtask2_id = task_mgr.add_subtask(
        parent_id=parent_id,
        title="Subtask 2",
        description="Second subtask"
    )
    
    # Check parent task has subtasks
    parent_task = task_mgr.get_task(parent_id)
    assert len(parent_task.get('subtasks', [])) == 2, f"Parent should have 2 subtasks, got {len(parent_task.get('subtasks', []))}"
    
    # Check subtask parent reference
    subtask = task_mgr.get_task(subtask1_id)
    assert subtask.get('parent_id') == parent_id, f"Subtask parent_id should be {parent_id}, got {subtask.get('parent_id')}"
    
    print("✅ Subtask creation passed")
    return [subtask1_id, subtask2_id]

def test_task_chain():
    """Test creating a task chain"""
    print("\n=== Testing Task Chain Creation ===")
    
    task_mgr = setup()
    
    # Create a task chain
    chain_id = task_mgr.create_task_chain(
        title="Complex Task",
        description="A task with multiple steps",
        subtasks=[
            {"title": "Step 1", "description": "First step"},
            {"title": "Step 2", "description": "Second step"},
            {"title": "Step 3", "description": "Final step"}
        ],
        priority=TaskManager.PRIORITY_CRITICAL,
        tags=["chain", "test"]
    )
    
    # Check chain created successfully
    chain = task_mgr.get_task(chain_id)
    assert chain is not None, "Chain should exist"
    assert len(chain.get('subtasks', [])) == 3, f"Chain should have 3 subtasks, got {len(chain.get('subtasks', []))}"
    
    # Get subtasks
    subtasks = task_mgr.get_task_subtasks(chain_id)
    assert len(subtasks) == 3, f"Should get 3 subtasks, got {len(subtasks)}"
    
    print("✅ Task chain creation passed")
    return chain_id

def test_task_completion(task_chain_id):
    """Test completing tasks and subtasks"""
    print("\n=== Testing Task Completion ===")
    
    task_mgr = setup()
    
    # Get subtasks
    subtasks = task_mgr.get_task_subtasks(task_chain_id)
    
    # Complete first subtask
    first_subtask_id = subtasks[0]['id']
    task_mgr.update_task_status(first_subtask_id, "completed", "First step done")
    
    # Check parent task progress updated
    chain = task_mgr.get_task(task_chain_id)
    assert chain.get('progress') > 0, f"Parent task progress should be > 0, got {chain.get('progress')}"
    print(f"Parent task progress after 1/3 subtasks: {chain.get('progress')}%")
    
    # Complete other subtasks
    for subtask in subtasks[1:]:
        task_mgr.update_task_status(subtask['id'], "completed", "Step done")
    
    # Check if parent task auto-completed
    chain = task_mgr.get_task(task_chain_id)
    assert chain.get('status') == "completed", f"Chain should auto-complete, status is {chain.get('status')}"
    assert chain.get('progress') == 100, f"Chain progress should be 100%, got {chain.get('progress')}%"
    
    print("✅ Task completion passed")

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

def test_stats():
    """Test task statistics"""
    print("\n=== Testing Task Statistics ===")
    
    # Start with a fresh environment for stats testing
    task_mgr = setup_fresh()
    
    # Create various tasks with different priorities
    task1_id = task_mgr.add_task(title="Task 1", description="Low priority task", priority=TaskManager.PRIORITY_LOW)
    task_mgr.add_task(title="Task 2", description="Normal priority task", priority=TaskManager.PRIORITY_NORMAL)
    task_mgr.add_task(title="Task 3", description="High priority task", priority=TaskManager.PRIORITY_HIGH) 
    task_mgr.add_task(title="Task 4", description="Critical priority task", priority=TaskManager.PRIORITY_CRITICAL)
    
    # Create a chain
    chain_id = task_mgr.create_task_chain(
        title="Chain", 
        description="Chain task",
        subtasks=[
            {"title": "Subtask 1"},
            {"title": "Subtask 2"}
        ]
    )
    
    # Complete a task
    task_mgr.update_task_status(task1_id, "completed")
    
    # Get stats
    stats = task_mgr.get_stats()
    
    # Check various stats
    assert stats.get('active_tasks') == 6, f"Should have 6 active tasks, got {stats.get('active_tasks')}"
    assert stats.get('completed_tasks') == 1, f"Should have 1 completed task, got {stats.get('completed_tasks')}"
    assert stats.get('priority_counts', {}).get('critical') == 1, f"Should have 1 critical task, got {stats.get('priority_counts', {}).get('critical')}"
    
    print(f"Stats: {json.dumps(stats, indent=2)}")
    print("✅ Task statistics passed")

def main():
    """Run all tests with proper setup and cleanup"""
    print("=== TaskManager Enhanced Tests ===")
    
    try:
        # Set up a clean environment
        if TEST_DIR.exists():
            shutil.rmtree(TEST_DIR)
        TEST_DIR.mkdir(exist_ok=True)
        
        # Run tests in sequence - each test should handle its own setup
        # and expect data from previous tests to be available

        # First, do basic task creation
        task_id = test_basic_task_creation()
        print(f"Created task ID: {task_id}")
        
        # Test updating the task we created
        test_task_updates(task_id)
        
        # Add subtasks to the main task
        subtask_ids = test_subtask_creation(task_id)
        print(f"Created subtask IDs: {subtask_ids}")
        
        # Create a separate task chain
        chain_id = test_task_chain()
        print(f"Created task chain ID: {chain_id}")
        
        # Test completing the chain tasks
        test_task_completion(chain_id)
        
        # Test searching and filtering
        test_task_search_and_filter()
        
        # Test overall statistics
        test_stats()
        
        print("\n✅ All tests completed successfully")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        raise
    finally:
        # Clean up
        if TEST_DIR.exists():
            shutil.rmtree(TEST_DIR)

if __name__ == "__main__":
    main()
