import json
import logging
import uuid
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

class TaskManager:
    """
    Enhanced TaskManager for handling complex task workflows.
    
    Features:
    - Task prioritization
    - Progress tracking
    - Subtask chaining
    - Dependency management
    - Task history and versioning
    """
    
    # Priority levels
    PRIORITY_CRITICAL = 100
    PRIORITY_HIGH = 75
    PRIORITY_NORMAL = 50
    PRIORITY_LOW = 25
    PRIORITY_MINIMAL = 10
    
    # Valid task statuses
    VALID_STATUSES = [
        "pending",      # Not started yet
        "in_progress",  # Currently being worked on
        "completed",    # Successfully finished
        "failed",       # Failed to complete
        "blocked",      # Waiting for other tasks or conditions
        "scheduled",    # Planned for future execution
        "canceled",     # Explicitly canceled
        "recurring",    # Repeating task
        "paused"        # Temporarily paused
    ]
    
    def __init__(self, memory_path: Path):
        """Initialize the TaskManager with the given memory path."""
        self.memory_path = memory_path
        self.tasks_dir = memory_path / "tasks"
        self.tasks_dir.mkdir(exist_ok=True, parents=True)
        
        # Task storage
        self.active_tasks_path = self.tasks_dir / "active_tasks.json"
        self.completed_tasks_path = self.tasks_dir / "completed_tasks.json"
        self.history_path = self.tasks_dir / "task_history.json"
        self.recurring_tasks_path = self.tasks_dir / "recurring_tasks.json"
        
        # Load saved tasks
        self.active_tasks = self._load_json(self.active_tasks_path, default=[])
        self.completed_tasks = self._load_json(self.completed_tasks_path, default=[])
        self.task_history = self._load_json(self.history_path, default=[])
        self.recurring_tasks = self._load_json(self.recurring_tasks_path, default=[])
        
        # Task relationship tracking
        self.dependencies = {}  # task_id -> [dependent_tasks]
        self.blockers = {}      # task_id -> [blocking_tasks]
        self.subtasks = {}      # parent_id -> [subtask_ids]
        self.parent_map = {}    # subtask_id -> parent_id
        
        # Initialize relationships from loaded data
        self._initialize_relationships()
        
        # Statistics tracking
        self.stats = {
            "total_tasks_created": 0,
            "total_tasks_completed": 0,
            "total_tasks_failed": 0,
            "total_modifications": 0,
            "total_progress_updates": 0,
            "total_chains_completed": 0,
            "last_backup_time": datetime.now().isoformat()
        }
        
        # Update/import legacy task data
        self._update_task_structure()
        
        # Perform recovery check
        self._recovery_check()
        
        logger.info(f"TaskManager initialized with {len(self.active_tasks)} active tasks")

    def _load_json(self, path: Path, default: Any = None) -> Any:
        try:
            if path.exists():
                with open(path, 'r') as f:
                    return json.load(f)
            return default if default is not None else {}
        except Exception as e:
            logger.error(f"Error loading {path}: {e}")
            return default if default is not None else {}

    def _save_json(self, path: Path, data: Any) -> bool:
        try:
            if path.exists():
                backup_path = path.with_suffix(".bak")
                with open(path, 'r') as f:
                    original_content = f.read()
                with open(backup_path, 'w') as f:
                    f.write(original_content)
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving {path}: {e}")
            if path.exists() and (path.with_suffix(".bak")).exists():
                try:
                    with open(path.with_suffix(".bak"), 'r') as f:
                        backup_content = f.read()
                    with open(path, 'w') as f:
                        f.write(backup_content)
                    logger.info(f"Restored {path} from backup")
                except Exception as restore_error:
                    logger.error(f"Failed restore {path}: {restore_error}")
            return False

    def _update_task_structure(self):
        """Update legacy task structure to current format."""
        for i, task in enumerate(self.active_tasks):
            # Ensure all required fields exist
            if 'priority' not in task:
                task['priority'] = self.PRIORITY_NORMAL
            if 'progress' not in task:
                task['progress'] = 0
            if 'estimated_time' not in task:
                task['estimated_time'] = None
            if 'parent_id' not in task:
                task['parent_id'] = None
            if 'subtasks' not in task:
                task['subtasks'] = []
            
            # Ensure status is valid
            if task.get('status') not in self.VALID_STATUSES:
                logger.warning(f"Task {task.get('id')}: invalid status '{task.get('status')}' changed to 'pending'")
                task['status'] = 'pending'
                
            self.active_tasks[i] = task
            
        # Also update completed tasks structure
        for i, task in enumerate(self.completed_tasks):
            if 'priority' not in task:
                task['priority'] = self.PRIORITY_NORMAL
            if 'progress' not in task:
                task['progress'] = 100  # Completed tasks are at 100%
            if 'estimated_time' not in task:
                task['estimated_time'] = None
            if 'parent_id' not in task:
                task['parent_id'] = None
            if 'subtasks' not in task:
                task['subtasks'] = []
                
            self.completed_tasks[i] = task
            
        # Save updates
        self._save_all()
            
    def _initialize_relationships(self):
        """Build relationship maps from task data."""
        # Reset relationship trackers
        self.dependencies = {}
        self.blockers = {}
        self.subtasks = {}
        self.parent_map = {}
        
        # Process all active tasks
        for task in self.active_tasks:
            tid = task.get('id')
            if not tid:
                continue
                
            # Initialize empty lists if needed
            if tid not in self.dependencies:
                self.dependencies[tid] = []
            if tid not in self.blockers:
                self.blockers[tid] = []
            if tid not in self.subtasks:
                self.subtasks[tid] = []
                
            # Process dependencies (tasks that depend on this task)
            for dep_id in task.get('dependencies', []):
                if dep_id not in self.dependencies:
                    self.dependencies[dep_id] = []
                self.dependencies[dep_id].append(tid)
                
            # Process blockers (tasks that block this task)
            for blocker_id in task.get('blockers', []):
                self.blockers[tid].append(blocker_id)
                
            # Process parent-child relationships
            parent_id = task.get('parent_id')
            if parent_id:
                self.parent_map[tid] = parent_id
                if parent_id not in self.subtasks:
                    self.subtasks[parent_id] = []
                if tid not in self.subtasks[parent_id]:
                    self.subtasks[parent_id].append(tid)
                    
            # Also process subtasks list
            for subtask_id in task.get('subtasks', []):
                if tid not in self.subtasks:
                    self.subtasks[tid] = []
                if subtask_id not in self.subtasks[tid]:
                    self.subtasks[tid].append(subtask_id)
                self.parent_map[subtask_id] = tid

    def _recovery_check(self):
        """Perform database integrity checks and fix inconsistencies."""
        try:
            logger.info("TaskManager recovery check")
            
            # Check for orphaned dependencies (dependencies for non-existent tasks)
            orphaned_deps = set()
            for task_id in list(self.dependencies.keys()):
                if not self._task_exists(task_id) and self.dependencies[task_id]:
                    logger.warning(f"Found orphaned dependencies for non-existent task {task_id}")
                    orphaned_deps.add(task_id)
            
            # Remove orphaned dependencies
            for task_id in orphaned_deps:
                del self.dependencies[task_id]
            
            # Check for blockers of non-existent tasks
            for task_id, blocker_list in list(self.blockers.items()):
                if not self._task_exists(task_id):
                    logger.warning(f"Found blockers for non-existent task {task_id}")
                    del self.blockers[task_id]
                else:
                    # Filter out non-existent blockers
                    valid_blockers = [b for b in blocker_list if self._task_exists(b)]
                    if len(valid_blockers) != len(blocker_list):
                        logger.warning(f"Removed {len(blocker_list) - len(valid_blockers)} non-existent blockers for task {task_id}")
                        self.blockers[task_id] = valid_blockers
            
            # Check for orphaned subtasks
            for parent_id, subtask_list in list(self.subtasks.items()):
                if not self._task_exists(parent_id):
                    logger.warning(f"Found subtasks for non-existent parent task {parent_id}")
                    # Don't delete - orphaned subtasks will be handled below
                else:
                    # Filter out non-existent subtasks
                    valid_subtasks = [s for s in subtask_list if self._task_exists(s)]
                    if len(valid_subtasks) != len(subtask_list):
                        logger.warning(f"Removed {len(subtask_list) - len(valid_subtasks)} non-existent subtasks for task {parent_id}")
                        self.subtasks[parent_id] = valid_subtasks
                        
                        # Update the parent task's subtasks list
                        for i, task in enumerate(self.active_tasks):
                            if task.get('id') == parent_id:
                                self.active_tasks[i]['subtasks'] = valid_subtasks
                                break
            
            # Check parent references to ensure they exist
            for child_id, parent_id in list(self.parent_map.items()):
                if not self._task_exists(parent_id):
                    logger.warning(f"Task {child_id} references non-existent parent {parent_id}, removing reference")
                    del self.parent_map[child_id]
                    
                    # Update the child task
                    for i, task in enumerate(self.active_tasks):
                        if task.get('id') == child_id:
                            self.active_tasks[i]['parent_id'] = None
                            break
            
            # Validate task statuses
            for i, task in enumerate(self.active_tasks):
                status = task.get('status')
                if status not in self.VALID_STATUSES:
                    logger.warning(f"Task {task.get('id')} has invalid status '{status}', setting to 'pending'")
                    self.active_tasks[i]['status'] = "pending"
                
                # Ensure progress is valid (0-100)
                progress = task.get('progress', 0)
                if not (isinstance(progress, (int, float)) and 0 <= progress <= 100):
                    logger.warning(f"Task {task.get('id')} has invalid progress value {progress}, setting to 0")
                    self.active_tasks[i]['progress'] = 0
            
            # Save all fixes
            self._save_all()
            logger.info("Recovery check completed successfully")
            
        except Exception as e:
            logger.error(f"Recovery check error: {e}")

    def _task_exists(self, task_id: str) -> bool:
        return any(t.get('id') == task_id for t in self.active_tasks) or \
               any(t.get('id') == task_id for t in self.completed_tasks)

    def _save_all(self):
        self.stats["last_backup_time"] = datetime.now().isoformat()
        self.stats["total_modifications"] += 1
        self._save_json(self.active_tasks_path, self.active_tasks)
        self._save_json(self.completed_tasks_path, self.completed_tasks)
        self._save_json(self.history_path, self.task_history)
        self._save_json(self.recurring_tasks_path, self.recurring_tasks)
        stats_path = self.tasks_dir / "task_stats.json"
        self._save_json(stats_path, self.stats)

    def add_task(self, title: str, description: str, priority: int = None, 
                 estimated_time: Optional[int] = None, tags: List[str] = None,
                 session_id: str = "", metadata: Dict[str, Any] = None,
                 task_id: str = None) -> str:
        """
        Create a new task with enhanced properties.
        
        Args:
            title: Short title of the task
            description: Detailed description of what the task involves
            priority: Priority level (use PRIORITY_* constants)
            estimated_time: Estimated time to complete in minutes
            tags: List of tags for categorization
            session_id: Optional session identifier
            metadata: Additional data to store with the task
            task_id: Custom task ID (generated if not provided)
            
        Returns:
            The task ID (either provided or generated)
        """
        # Generate task ID if not provided
        if not task_id:
            task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            
        # Use default priority if not specified
        if priority is None:
            priority = self.PRIORITY_NORMAL
            
        # Create the task with enhanced fields
        task = {
            "id": task_id,
            "title": title,
            "description": description,
            "status": "pending",
            "priority": priority,
            "progress": 0,
            "estimated_time": estimated_time,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "dependencies": [],
            "blockers": [],
            "tags": tags or [],
            "metadata": metadata or {},
            "version": 1,
            "history": [],
            "parent_id": None,
            "subtasks": [],
            "session_id": session_id
        }
        
        # Add the task to active tasks
        self.active_tasks.append(task)
        
        # Initialize relationships
        if task_id not in self.dependencies:
            self.dependencies[task_id] = []
        if task_id not in self.blockers:
            self.blockers[task_id] = []
        if task_id not in self.subtasks:
            self.subtasks[task_id] = []
            
        # Update stats and save
        self.stats["total_tasks_created"] += 1
        self._save_all()
        
        logger.info(f"Added task: {task_id} - {title} (priority: {priority})")
        return task_id

    def add_subtask(self, parent_id: str, title: str, description: str, 
                    priority: int = None, estimated_time: Optional[int] = None,
                    tags: List[str] = None, metadata: Dict[str, Any] = None,
                    subtask_id: str = None, auto_block: bool = True) -> str:
        """
        Create a subtask under a parent task.
        
        Args:
            parent_id: ID of the parent task
            title: Short title of the subtask
            description: Detailed description
            priority: Priority level (defaults to parent's priority if None)
            estimated_time: Estimated time to complete in minutes
            tags: List of tags for categorization
            metadata: Additional data to store with the task
            subtask_id: Custom subtask ID (generated if not provided)
            auto_block: If True, parent task is blocked until all subtasks complete
            
        Returns:
            The subtask ID (either provided or generated)
        """
        # Check if parent task exists
        parent_task = self.get_task(parent_id)
        if not parent_task:
            logger.error(f"Cannot add subtask: parent task {parent_id} not found")
            return None
            
        # Generate subtask ID if not provided
        if not subtask_id:
            subtask_id = f"subtask_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            
        # Use parent's priority if not specified
        if priority is None:
            priority = parent_task.get('priority', self.PRIORITY_NORMAL)
            
        # Create the subtask with enhanced fields and parent reference
        subtask = {
            "id": subtask_id,
            "title": title,
            "description": description,
            "status": "pending",
            "priority": priority,
            "progress": 0,
            "estimated_time": estimated_time,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "dependencies": [],
            "blockers": [],
            "tags": tags or [],
            "metadata": metadata or {},
            "version": 1,
            "history": [],
            "parent_id": parent_id,
            "subtasks": []
        }
        
        # Add the subtask to active tasks
        self.active_tasks.append(subtask)
        
        # Update parent task's subtasks list
        for i, task in enumerate(self.active_tasks):
            if task.get('id') == parent_id:
                if 'subtasks' not in task:
                    self.active_tasks[i]['subtasks'] = []
                self.active_tasks[i]['subtasks'].append(subtask_id)
                break
                
        # Update relationship maps
        if parent_id not in self.subtasks:
            self.subtasks[parent_id] = []
        self.subtasks[parent_id].append(subtask_id)
        self.parent_map[subtask_id] = parent_id
        
        # Add dependency relationship (parent depends on subtask)
        if auto_block and parent_id not in subtask.get('dependencies', []):
            subtask['dependencies'].append(parent_id)
            if parent_id not in self.dependencies:
                self.dependencies[parent_id] = []
            self.dependencies[parent_id].append(subtask_id)
            
        # Initialize other relationships
        if subtask_id not in self.dependencies:
            self.dependencies[subtask_id] = []
        if subtask_id not in self.blockers:
            self.blockers[subtask_id] = []
        if subtask_id not in self.subtasks:
            self.subtasks[subtask_id] = []
            
        # Update stats and save
        self.stats["total_tasks_created"] += 1
        self._save_all()
        
        logger.info(f"Added subtask {subtask_id} under parent {parent_id}")
        return subtask_id

    def update_task_progress(self, task_id: str, progress: int, message: str = None) -> bool:
        """
        Update the completion progress of a task.
        
        Args:
            task_id: ID of the task to update
            progress: Completion percentage (0-100)
            message: Optional message describing the progress update
            
        Returns:
            True if the task was updated, False otherwise
        """
        # Validate progress value
        if not isinstance(progress, (int, float)) or not (0 <= progress <= 100):
            logger.error(f"Invalid progress value: {progress}. Must be between 0-100.")
            return False
            
        # Find the task
        for i, task in enumerate(self.active_tasks):
            if task.get('id') == task_id:
                old_progress = task.get('progress', 0)
                
                # Skip if no change
                if old_progress == progress:
                    return True
                    
                # Update progress
                self.active_tasks[i]['progress'] = progress
                self.active_tasks[i]['updated_at'] = datetime.now().isoformat()
                self.active_tasks[i]['version'] += 1
                
                # Add to history
                if 'history' not in self.active_tasks[i]:
                    self.active_tasks[i]['history'] = []
                    
                history_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "field": "progress",
                    "old_value": old_progress,
                    "new_value": progress
                }
                
                if message:
                    history_entry["message"] = message
                    
                self.active_tasks[i]['history'].append(history_entry)
                
                # Auto-update status based on progress if needed
                if progress == 100 and self.active_tasks[i]['status'] in ['pending', 'in_progress']:
                    # Automatically complete the task
                    return self.update_task_status(task_id, "completed", message="Auto-completed due to 100% progress")
                
                # Save changes
                self.stats["total_progress_updates"] += 1
                self._save_all()
                logger.info(f"Task {task_id} progress updated: {old_progress}% → {progress}%")
                return True
                
        logger.warning(f"Task {task_id} not found for progress update")
        return False
    
    def update_task_status(self, task_id: str, new_status: str, message: str = None) -> bool:
        """
        Update the status of a task.
        
        Args:
            task_id: ID of the task to update
            new_status: New status (must be one of the VALID_STATUSES)
            message: Optional message explaining the status change
            
        Returns:
            True if the task was updated, False otherwise
        """
        # Validate status
        if new_status not in self.VALID_STATUSES:
            logger.error(f"Invalid status {new_status}. Must be one of: {', '.join(self.VALID_STATUSES)}")
            return False
            
        # Find the task
        for i, task in enumerate(self.active_tasks):
            if task.get('id') == task_id:
                old_status = task.get('status')
                
                # Skip if no change
                if old_status == new_status:
                    return True
                    
                # Update status
                self.active_tasks[i]['status'] = new_status
                self.active_tasks[i]['updated_at'] = datetime.now().isoformat()
                self.active_tasks[i]['version'] += 1
                
                # Add to history
                if 'history' not in self.active_tasks[i]:
                    self.active_tasks[i]['history'] = []
                    
                history_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "field": "status",
                    "old_value": old_status,
                    "new_value": new_status
                }
                
                if message:
                    history_entry["message"] = message
                    
                self.active_tasks[i]['history'].append(history_entry)
                
                # Handle special status changes
                if new_status == "completed":
                    # Set completion timestamp and progress to 100%
                    self.active_tasks[i]['completed_at'] = datetime.now().isoformat()
                    self.active_tasks[i]['progress'] = 100
                    self.stats["total_tasks_completed"] += 1
                    
                    # Move task to completed list and update dependencies
                    self._handle_task_completion(task_id, self.active_tasks[i])
                    
                elif new_status == "failed":
                    # Set failure timestamp
                    self.active_tasks[i]['failed_at'] = datetime.now().isoformat()
                    self.stats["total_tasks_failed"] += 1
                
                # Save changes
                self._save_all()
                logger.info(f"Task {task_id} status updated: {old_status} → {new_status}")
                return True
                
        logger.warning(f"Task {task_id} not found for status update")
        return False

    def _handle_task_completion(self, task_id: str, task: Dict[str, Any]):
        """
        Handle the completion of a task, including subtask and dependency management.
        
        This includes:
        1. Updating dependent tasks that were waiting on this task
        2. Checking if this was a subtask and updating parent task progress
        3. Moving the task to completed_tasks list
        4. Recording the completion in task history
        5. Checking if a task chain has been completed
        
        Args:
            task_id: ID of the completed task
            task: The task data dictionary
        """
        # Step 1: Process tasks that depend on this task
        dep_tasks = self.dependencies.get(task_id, [])
        for d_id in dep_tasks:
            for i, dep_task in enumerate(self.active_tasks):
                if dep_task.get('id') == d_id:
                    # Remove from blockers list if present
                    if task_id in dep_task.get('blockers', []):
                        self.active_tasks[i]['blockers'].remove(task_id)
                    
                    # If no more blockers and task is blocked, set to pending
                    if not self.active_tasks[i]['blockers'] and self.active_tasks[i]['status'] == "blocked":
                        self.active_tasks[i]['status'] = "pending"
                        self.active_tasks[i]['updated_at'] = datetime.now().isoformat()
                        
        # Step 2: If this is a subtask, update parent task progress
        parent_id = task.get('parent_id')
        if parent_id:
            self._update_parent_task_progress(parent_id)
            
        # Step 3: Move task to completed list
        self.completed_tasks.append(task)
        self.active_tasks = [t for t in self.active_tasks if t.get('id') != task_id]
        
        # Step 4: Record completion in task history
        history_entry = {
            "id": f"history_{int(time.time())}_{uuid.uuid4().hex[:8]}",
            "task_id": task_id,
            "title": task.get('title'),
            "action": "completed",
            "timestamp": datetime.now().isoformat(),
            "details": task
        }
        self.task_history.append(history_entry)
        
        # Step 5: Check for chain completion
        self._check_task_chain_completion(task_id)
        
        logger.info(f"Task completion handled: {task_id}")
        
    def _update_parent_task_progress(self, parent_id: str) -> None:
        """
        Update a parent task's progress based on subtask completion status.
        
        Args:
            parent_id: ID of the parent task to update
        """
        parent_task = None
        parent_idx = None
        
        # Find the parent task
        for i, task in enumerate(self.active_tasks):
            if task.get('id') == parent_id:
                parent_task = task
                parent_idx = i
                break
        
        if not parent_task:
            logger.warning(f"Parent task {parent_id} not found for progress update")
            return
            
        # Get list of subtasks
        subtask_ids = parent_task.get('subtasks', [])
        if not subtask_ids:
            return
            
        # Calculate progress based on subtask status
        total_subtasks = len(subtask_ids)
        completed_subtasks = 0
        total_progress = 0
        
        # Check each subtask
        for subtask_id in subtask_ids:
            # Look in active tasks
            subtask = next((t for t in self.active_tasks if t.get('id') == subtask_id), None)
            
            if subtask:
                # Active task - add its progress percentage
                if subtask.get('status') == 'completed':
                    completed_subtasks += 1
                    total_progress += 100  # Completed tasks are at 100%
                else:
                    total_progress += subtask.get('progress', 0)
            else:
                # Check in completed tasks
                subtask = next((t for t in self.completed_tasks if t.get('id') == subtask_id), None)
                if subtask:
                    completed_subtasks += 1
                    total_progress += 100  # Completed tasks are at 100%
        
        # Calculate average progress
        avg_progress = int(total_progress / max(1, total_subtasks))
        
        # Update parent task progress
        if parent_idx is not None:
            old_progress = self.active_tasks[parent_idx].get('progress', 0)
            self.active_tasks[parent_idx]['progress'] = avg_progress
            
            # Add history entry
            if 'history' not in self.active_tasks[parent_idx]:
                self.active_tasks[parent_idx]['history'] = []
                
            self.active_tasks[parent_idx]['history'].append({
                "timestamp": datetime.now().isoformat(),
                "field": "progress",
                "old_value": old_progress,
                "new_value": avg_progress,
                "message": f"Auto-updated by subtask completion ({completed_subtasks}/{total_subtasks} subtasks complete)"
            })
            
            # Update timestamp
            self.active_tasks[parent_idx]['updated_at'] = datetime.now().isoformat()
            
            logger.info(f"Updated parent task {parent_id} progress: {old_progress}% → {avg_progress}%")
            
            # If all subtasks complete, auto-complete parent task
            if completed_subtasks == total_subtasks:
                self.update_task_status(parent_id, "completed", 
                                        message=f"Auto-completed: all {total_subtasks} subtasks finished")
    
    def _check_task_chain_completion(self, task_id: str) -> None:
        """
        Check if a task chain has been completed.
        A chain is a series of related tasks (parent-child relationships).
        
        Args:
            task_id: ID of the recently completed task
        """
        # Get parent ID, if any
        task = next((t for t in self.completed_tasks if t.get('id') == task_id), None)
        if not task:
            return
            
        parent_id = task.get('parent_id')
        if not parent_id:
            # This was a top-level task, check if it had subtasks that are all completed
            subtask_ids = task.get('subtasks', [])
            if not subtask_ids:
                return
                
            all_completed = True
            for subtask_id in subtask_ids:
                # If any subtask is still active, chain is not completed
                if any(t.get('id') == subtask_id for t in self.active_tasks):
                    all_completed = False
                    break
            
            if all_completed:
                self.stats["total_chains_completed"] += 1
                logger.info(f"Task chain completed: {task_id} with {len(subtask_ids)} subtasks")

    def update_task_priority(self, task_id: str, priority: int) -> bool:
        """
        Update the priority of a task.
        
        Args:
            task_id: ID of the task to update
            priority: New priority level (recommended to use PRIORITY_* constants)
            
        Returns:
            True if task was updated, False otherwise
        """
        # Find the task
        for i, task in enumerate(self.active_tasks):
            if task.get('id') == task_id:
                old_priority = task.get('priority', self.PRIORITY_NORMAL)
                
                # Skip if no change
                if old_priority == priority:
                    return True
                    
                # Update priority
                self.active_tasks[i]['priority'] = priority
                self.active_tasks[i]['updated_at'] = datetime.now().isoformat()
                self.active_tasks[i]['version'] += 1
                
                # Add to history
                if 'history' not in self.active_tasks[i]:
                    self.active_tasks[i]['history'] = []
                    
                self.active_tasks[i]['history'].append({
                    "timestamp": datetime.now().isoformat(),
                    "field": "priority",
                    "old_value": old_priority,
                    "new_value": priority
                })
                
                # Save changes
                self._save_all()
                logger.info(f"Task {task_id} priority updated: {old_priority} → {priority}")
                return True
                
        logger.warning(f"Task {task_id} not found for priority update")
        return False
    
    def create_task_chain(self, title: str, description: str, subtasks: List[Dict[str, Any]], 
                         priority: int = None, tags: List[str] = None, 
                         metadata: Dict[str, Any] = None) -> str:
        """
        Create a parent task with a series of subtasks in one operation.
        
        Args:
            title: Title of the parent task
            description: Description of the parent task
            subtasks: List of dictionaries with subtask details
                     [{"title": "...", "description": "...", "priority": int}]
            priority: Priority for the parent task
            tags: List of tags for the parent task
            metadata: Additional metadata for the parent task
            
        Returns:
            ID of the created parent task
        """
        # Create parent task
        parent_id = self.add_task(
            title=title,
            description=description,
            priority=priority,
            tags=tags,
            metadata=metadata
        )
        
        # Create all subtasks
        for i, subtask_data in enumerate(subtasks):
            subtask_title = subtask_data.get('title', f"Subtask {i+1}")
            subtask_desc = subtask_data.get('description', f"Step {i+1} of {title}")
            subtask_priority = subtask_data.get('priority', None)  # Will inherit parent's if None
            subtask_tags = subtask_data.get('tags', None)
            subtask_metadata = subtask_data.get('metadata', None)
            
            # Create the subtask
            self.add_subtask(
                parent_id=parent_id,
                title=subtask_title,
                description=subtask_desc,
                priority=subtask_priority,
                tags=subtask_tags,
                metadata=subtask_metadata
            )
        
        logger.info(f"Created task chain: {parent_id} with {len(subtasks)} subtasks")
        return parent_id
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a task by ID, checking both active and completed tasks.
        
        Args:
            task_id: ID of the task to retrieve
            
        Returns:
            Copy of the task dictionary, or None if not found
        """
        # Check active tasks
        for t in self.active_tasks:
            if t.get('id') == task_id:
                return t.copy()
                
        # Check completed tasks
        for t in self.completed_tasks:
            if t.get('id') == task_id:
                return t.copy()
                
        return None

    def delete_task(self, task_id: str) -> bool:
        task = next((t for t in self.active_tasks if t.get('id') == task_id), None)
        if task:
            self.active_tasks = [t for t in self.active_tasks if t.get('id') != task_id]
            history_entry = {
                "id": f"history_{int(time.time())}_{uuid.uuid4().hex[:8]}",
                "task_id": task_id,
                "title": task.get('title'),
                "action": "deleted",
                "timestamp": datetime.now().isoformat(),
                "details": task
            }
            self.task_history.append(history_entry)
            if task_id in self.dependencies:
                del self.dependencies[task_id]
            if task_id in self.blockers:
                del self.blockers[task_id]
            for dep_id, dependents in list(self.dependencies.items()):
                if task_id in dependents:
                    self.dependencies[dep_id] = [d for d in dependents if d != task_id]
            for t_id, b in list(self.blockers.items()):
                if task_id in b:
                    self.blockers[t_id] = [x for x in b if x != task_id]
            self._save_all()
            logger.info(f"Deleted task {task_id}")
            return True
        logger.warning(f"Task {task_id} not found for deletion")
        return False

    def create_backup(self) -> str:
        try:
            backup_dir = self.tasks_dir / f"backups/bk_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_dir.mkdir(parents=True, exist_ok=True)
            self._save_json(backup_dir / "active_tasks.json", self.active_tasks)
            self._save_json(backup_dir / "completed_tasks.json", self.completed_tasks)
            self._save_json(backup_dir / "task_history.json", self.task_history)
            self._save_json(backup_dir / "recurring_tasks.json", self.recurring_tasks)
            self._save_json(backup_dir / "task_stats.json", self.stats)
            logger.info(f"Task backup at {backup_dir}")
            return str(backup_dir)
        except Exception as e:
            logger.error(f"Backup error: {e}")
            return ""

    def restore_from_backup(self, backup_path: str) -> bool:
        try:
            bd = Path(backup_path)
            if not bd.exists() or not bd.is_dir():
                logger.error(f"Backup path invalid: {backup_path}")
                return False
            active_tasks = self._load_json(bd / "active_tasks.json", default=[])
            completed_tasks = self._load_json(bd / "completed_tasks.json", default=[])
            task_history = self._load_json(bd / "task_history.json", default=[])
            recurring_tasks = self._load_json(bd / "recurring_tasks.json", default=[])
            current_backup = self.create_backup()
            self.active_tasks = active_tasks
            self.completed_tasks = completed_tasks
            self.task_history = task_history
            self.recurring_tasks = recurring_tasks
            self._initialize_relationships()
            self._save_all()
            logger.info(f"Restored tasks from {backup_path}, old state in {current_backup}")
            return True
        except Exception as e:
            logger.error(f"Restore error: {e}")
            return False

    def get_active_tasks(self, sort_by_priority: bool = True) -> List[Dict[str, Any]]:
        """
        Get all active tasks, optionally sorted by priority.
        
        Args:
            sort_by_priority: If True, sort tasks by priority (highest first)
            
        Returns:
            List of active task dictionaries (copies)
        """
        tasks = [t.copy() for t in self.active_tasks]
        
        if sort_by_priority:
            # Sort by priority (higher values first)
            tasks.sort(key=lambda t: t.get('priority', self.PRIORITY_NORMAL), reverse=True)
            
        return tasks
    
    def get_tasks_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Get all tasks with a specific status.
        
        Args:
            status: Status to filter by (must be one of VALID_STATUSES)
            
        Returns:
            List of matching task dictionaries (copies)
        """
        if status not in self.VALID_STATUSES:
            logger.warning(f"Invalid status {status} for task query")
            return []
            
        return [t.copy() for t in self.active_tasks if t.get('status') == status]
    
    def get_tasks_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        """
        Get all tasks with a specific tag.
        
        Args:
            tag: Tag to search for
            
        Returns:
            List of matching task dictionaries (copies)
        """
        return [t.copy() for t in self.active_tasks 
                if tag in t.get('tags', [])]
    
    def search_tasks(self, query: str, include_completed: bool = False) -> List[Dict[str, Any]]:
        """
        Search for tasks containing the query string in title or description.
        
        Args:
            query: Search string (case-insensitive)
            include_completed: Whether to include completed tasks in the search
            
        Returns:
            List of matching task dictionaries (copies)
        """
        query = query.lower()
        results = []
        
        # Search active tasks
        for task in self.active_tasks:
            title = task.get('title', '').lower()
            description = task.get('description', '').lower()
            
            if query in title or query in description:
                results.append(task.copy())
        
        # Search completed tasks if requested
        if include_completed:
            for task in self.completed_tasks:
                title = task.get('title', '').lower()
                description = task.get('description', '').lower()
                
                if query in title or query in description:
                    results.append(task.copy())
        
        return results
    
    def get_task_subtasks(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Get all subtasks of a given task.
        
        Args:
            task_id: ID of the parent task
            
        Returns:
            List of subtask dictionaries (copies)
        """
        task = self.get_task(task_id)
        if not task:
            return []
            
        subtask_ids = task.get('subtasks', [])
        if not subtask_ids:
            return []
            
        # Gather subtasks from both active and completed lists
        subtasks = []
        for subtask_id in subtask_ids:
            # Check active tasks
            subtask = next((t.copy() for t in self.active_tasks if t.get('id') == subtask_id), None)
            if subtask:
                subtasks.append(subtask)
                continue
                
            # Check completed tasks
            subtask = next((t.copy() for t in self.completed_tasks if t.get('id') == subtask_id), None)
            if subtask:
                subtasks.append(subtask)
        
        return subtasks
        
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about tasks and task management.
        
        Returns:
            Dictionary of statistics
        """
        # Count tasks by status
        status_counts = {}
        for status in self.VALID_STATUSES:
            status_counts[status] = sum(1 for t in self.active_tasks if t.get('status') == status)
            
        # Count tasks by priority level
        priority_counts = {
            "critical": sum(1 for t in self.active_tasks if t.get('priority', 0) >= self.PRIORITY_CRITICAL),
            "high": sum(1 for t in self.active_tasks if self.PRIORITY_HIGH <= t.get('priority', 0) < self.PRIORITY_CRITICAL),
            "normal": sum(1 for t in self.active_tasks if self.PRIORITY_LOW < t.get('priority', 0) < self.PRIORITY_HIGH),
            "low": sum(1 for t in self.active_tasks if t.get('priority', 0) <= self.PRIORITY_LOW)
        }
        
        # Update basic stats
        self.stats.update({
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len(self.completed_tasks),
            "recurring_tasks": len(self.recurring_tasks),
            "history_entries": len(self.task_history),
            "status_counts": status_counts,
            "priority_counts": priority_counts,
            "subtask_relationships": len(self.subtasks),
            "task_chains": sum(1 for t in self.active_tasks if t.get('subtasks'))
        })
        
        return self.stats.copy()
