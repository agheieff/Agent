import json
import logging
import uuid
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any, Set, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """Task status enumeration for improved tracking"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SCHEDULED = "scheduled"
    CANCELED = "canceled"
    RECURRING = "recurring"

class TaskPriority(Enum):
    """Task priority enumeration"""
    CRITICAL = 5
    HIGH = 4
    MEDIUM = 3
    LOW = 2
    MAINTENANCE = 1

class TaskManager:
    """
    Enhanced task manager for improved goal tracking and scheduling.
    
    Features:
    - Task dependencies (subtasks and blockers)
    - Task versioning
    - History tracking
    - Recurring tasks
    - Scheduling with time windows
    - Task state transitions
    - Persistence with automatic backup
    """
    
    def __init__(self, memory_path: Path):
        # Core paths
        self.memory_path = memory_path
        self.tasks_dir = memory_path / "tasks"
        self.tasks_dir.mkdir(exist_ok=True, parents=True)
        
        self.active_tasks_path = self.tasks_dir / "active_tasks.json"
        self.completed_tasks_path = self.tasks_dir / "completed_tasks.json"
        self.history_path = self.tasks_dir / "task_history.json"
        self.recurring_tasks_path = self.tasks_dir / "recurring_tasks.json"
        
        # Task collections
        self.active_tasks = self._load_json(self.active_tasks_path, default=[])
        self.completed_tasks = self._load_json(self.completed_tasks_path, default=[])
        self.task_history = self._load_json(self.history_path, default=[])
        self.recurring_tasks = self._load_json(self.recurring_tasks_path, default=[])
        
        # Task relationships
        self.dependencies = {}  # task_id -> [dependent_task_ids]
        self.blockers = {}      # task_id -> [blocker_task_ids]
        
        # Initialize dependencies from loaded tasks
        self._initialize_relationships()
        
        # Statistics tracking
        self.stats = {
            "total_tasks_created": 0,
            "total_tasks_completed": 0,
            "total_tasks_failed": 0,
            "total_modifications": 0,
            "last_backup_time": datetime.now().isoformat()
        }
        
        # Perform recovery check on startup
        self._recovery_check()
        logger.info(f"TaskManager initialized with {len(self.active_tasks)} active tasks")

    def _load_json(self, path: Path, default: Any = None) -> Any:
        """Load JSON data from file with error handling"""
        try:
            if path.exists():
                with open(path, 'r') as f:
                    return json.load(f)
            return default if default is not None else {}
        except Exception as e:
            logger.error(f"Error loading {path}: {e}")
            return default if default is not None else {}

    def _save_json(self, path: Path, data: Any) -> bool:
        """Save JSON data to file with error handling and backup"""
        try:
            # Create backup of existing file
            if path.exists():
                backup_path = path.with_suffix(f".bak")
                with open(path, 'r') as f:
                    original_content = f.read()
                with open(backup_path, 'w') as f:
                    f.write(original_content)
                    
            # Write new data
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving {path}: {e}")
            # Try to restore from backup if save failed
            if path.exists() and backup_path.exists():
                try:
                    with open(backup_path, 'r') as f:
                        backup_content = f.read()
                    with open(path, 'w') as f:
                        f.write(backup_content)
                    logger.info(f"Restored {path} from backup after failed save")
                except Exception as restore_error:
                    logger.error(f"Failed to restore {path} from backup: {restore_error}")
            return False
            
    def _initialize_relationships(self):
        """Initialize dependency and blocker relationships from loaded tasks"""
        self.dependencies = {}
        self.blockers = {}
        
        # Process active tasks
        for task in self.active_tasks:
            task_id = task.get('id')
            if not task_id:
                continue
                
            # Initialize empty lists for this task
            if task_id not in self.dependencies:
                self.dependencies[task_id] = []
            if task_id not in self.blockers:
                self.blockers[task_id] = []
                
            # Add dependencies
            for dep_id in task.get('dependencies', []):
                if dep_id not in self.dependencies:
                    self.dependencies[dep_id] = []
                self.dependencies[dep_id].append(task_id)
                
            # Add blockers
            for blocker_id in task.get('blockers', []):
                self.blockers[task_id].append(blocker_id)

    def _recovery_check(self):
        """Perform recovery check and fix any inconsistencies"""
        try:
            logger.info("Performing task recovery check")
            
            # Check for orphaned dependencies
            orphaned_deps = set()
            for task_id in list(self.dependencies.keys()):
                if not self._task_exists(task_id) and self.dependencies[task_id]:
                    logger.warning(f"Found orphaned dependencies for non-existent task {task_id}")
                    orphaned_deps.add(task_id)
            
            # Remove orphaned dependencies
            for task_id in orphaned_deps:
                del self.dependencies[task_id]
                
            # Check for invalid blockers
            for task_id, blockers in list(self.blockers.items()):
                if not self._task_exists(task_id):
                    logger.warning(f"Found blockers for non-existent task {task_id}")
                    del self.blockers[task_id]
                else:
                    # Remove non-existent blockers
                    valid_blockers = [b for b in blockers if self._task_exists(b)]
                    if len(valid_blockers) != len(blockers):
                        logger.warning(f"Removed non-existent blockers for task {task_id}")
                        self.blockers[task_id] = valid_blockers
                        
            # Check for tasks with invalid status
            for i, task in enumerate(self.active_tasks):
                status = task.get('status')
                if status not in [s.value for s in TaskStatus]:
                    logger.warning(f"Task {task.get('id')} has invalid status {status}, setting to PENDING")
                    self.active_tasks[i]['status'] = TaskStatus.PENDING.value
                    
            # Save changes if recovery was needed
            if orphaned_deps or any(not self._task_exists(task_id) for task_id in self.blockers):
                self._save_all()
                logger.info("Recovery completed and saved")
                
        except Exception as e:
            logger.error(f"Error during recovery check: {e}")

    def _task_exists(self, task_id: str) -> bool:
        """Check if a task exists in active or completed tasks"""
        return any(t.get('id') == task_id for t in self.active_tasks) or \
               any(t.get('id') == task_id for t in self.completed_tasks)

    def _save_all(self):
        """Save all task data with backup protection"""
        # Track stats before saving
        self.stats["last_backup_time"] = datetime.now().isoformat()
        self.stats["total_modifications"] += 1
        
        # Save each data file
        self._save_json(self.active_tasks_path, self.active_tasks)
        self._save_json(self.completed_tasks_path, self.completed_tasks)
        self._save_json(self.history_path, self.task_history)
        self._save_json(self.recurring_tasks_path, self.recurring_tasks)
        
        # Save stats
        stats_path = self.tasks_dir / "task_stats.json"
        self._save_json(stats_path, self.stats)

    def add_task(self, title: str, description: str, task_type: str = "user", 
                 priority: str = "MEDIUM", due_date: Optional[str] = None,
                 dependencies: List[str] = None, blockers: List[str] = None,
                 tags: List[str] = None, metadata: Dict[str, Any] = None) -> str:
        """
        Add a new task with enhanced metadata
        
        Args:
            title: Task title
            description: Task description
            task_type: Task type (system, user, maintenance)
            priority: Task priority (from TaskPriority enum)
            due_date: Optional due date as ISO format string
            dependencies: List of task IDs this task depends on
            blockers: List of task IDs blocking this task
            tags: List of tags for categorization
            metadata: Additional metadata for the task
            
        Returns:
            The ID of the created task
        """
        # Generate unique ID for the task
        task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        # Validate and normalize priority
        try:
            priority_enum = TaskPriority[priority] if isinstance(priority, str) else priority
            priority_value = priority_enum.value
        except (KeyError, AttributeError):
            priority_value = TaskPriority.MEDIUM.value
            
        # Create task object
        task = {
            "id": task_id,
            "title": title,
            "description": description,
            "type": task_type,
            "priority": priority_value,
            "status": TaskStatus.PENDING.value,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "due_date": due_date,
            "dependencies": dependencies or [],
            "blockers": blockers or [],
            "tags": tags or [],
            "metadata": metadata or {},
            "version": 1,
            "history": []
        }
        
        # Update relationships
        if blockers:
            self.blockers[task_id] = blockers.copy()
            
        if dependencies:
            for dep_id in dependencies:
                if dep_id not in self.dependencies:
                    self.dependencies[dep_id] = []
                self.dependencies[dep_id].append(task_id)
        
        # Add to active tasks
        self.active_tasks.append(task)
        
        # Update stats
        self.stats["total_tasks_created"] += 1
        
        # Save changes
        self._save_all()
        
        logger.info(f"Added new task: {task_id} - {title}")
        return task_id
        
    def add_recurring_task(self, title: str, description: str, 
                          interval_days: int, priority: str = "LOW",
                          task_type: str = "maintenance", tags: List[str] = None,
                          metadata: Dict[str, Any] = None) -> str:
        """
        Add a recurring task that gets regenerated at specified intervals
        
        Args:
            title: Task title
            description: Task description
            interval_days: How often to regenerate the task (in days)
            priority: Task priority
            task_type: Task type
            tags: List of tags for categorization
            metadata: Additional metadata for the recurring task
            
        Returns:
            The ID of the recurring task definition
        """
        # Generate unique ID for the recurring task
        recurring_id = f"recurring_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        # Create recurring task definition
        recurring_task = {
            "id": recurring_id,
            "title": title,
            "description": description,
            "interval_days": interval_days,
            "priority": priority,
            "type": task_type,
            "tags": tags or [],
            "metadata": metadata or {},
            "last_generated": None,
            "next_generation": datetime.now().isoformat(),
            "created_at": datetime.now().isoformat(),
            "active": True
        }
        
        # Add to recurring tasks
        self.recurring_tasks.append(recurring_task)
        
        # Save changes
        self._save_all()
        
        logger.info(f"Added recurring task: {recurring_id} - {title} (every {interval_days} days)")
        return recurring_id
        
    def process_recurring_tasks(self) -> List[str]:
        """
        Process recurring tasks and generate new tasks as needed
        
        Returns:
            List of IDs of newly generated tasks
        """
        current_time = datetime.now()
        new_task_ids = []
        
        for i, recurring in enumerate(self.recurring_tasks):
            if not recurring.get('active', True):
                continue
                
            next_gen = recurring.get('next_generation')
            if not next_gen:
                # Initialize next generation time if not set
                self.recurring_tasks[i]['next_generation'] = current_time.isoformat()
                continue
                
            try:
                next_gen_time = datetime.fromisoformat(next_gen)
                if current_time >= next_gen_time:
                    # Time to generate a new task
                    task_id = self.add_task(
                        title=f"{recurring['title']} (Recurring {current_time.strftime('%Y-%m-%d')})",
                        description=recurring['description'],
                        task_type=recurring.get('type', 'maintenance'),
                        priority=recurring.get('priority', 'LOW'),
                        tags=recurring.get('tags', []) + ['recurring'],
                        metadata={
                            **(recurring.get('metadata', {})),
                            'recurring_id': recurring['id'],
                            'recurring_generation': current_time.isoformat()
                        }
                    )
                    
                    # Update recurring task
                    self.recurring_tasks[i]['last_generated'] = current_time.isoformat()
                    interval = recurring.get('interval_days', 7)
                    next_time = current_time + timedelta(days=interval)
                    self.recurring_tasks[i]['next_generation'] = next_time.isoformat()
                    
                    new_task_ids.append(task_id)
                    logger.info(f"Generated recurring task {task_id} from {recurring['id']}")
            except Exception as e:
                logger.error(f"Error processing recurring task {recurring.get('id')}: {e}")
                
        if new_task_ids:
            self._save_all()
            
        return new_task_ids
        
    def update_task_status(self, task_id: str, new_status: str, 
                         note: Optional[str] = None) -> bool:
        """
        Update the status of a task with history tracking
        
        Args:
            task_id: ID of the task to update
            new_status: New status value from TaskStatus enum
            note: Optional note about the status change
            
        Returns:
            True if successful, False otherwise
        """
        # Validate status
        try:
            new_status_enum = TaskStatus[new_status] if isinstance(new_status, str) else new_status
            new_status_value = new_status_enum.value
        except (KeyError, AttributeError):
            logger.error(f"Invalid task status: {new_status}")
            return False
            
        # Find task
        for i, task in enumerate(self.active_tasks):
            if task.get('id') == task_id:
                old_status = task.get('status')
                
                # Create history entry
                history_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "field": "status",
                    "old_value": old_status,
                    "new_value": new_status_value,
                    "note": note
                }
                
                # Update task
                self.active_tasks[i]['status'] = new_status_value
                self.active_tasks[i]['updated_at'] = datetime.now().isoformat()
                self.active_tasks[i]['version'] += 1
                
                if 'history' not in self.active_tasks[i]:
                    self.active_tasks[i]['history'] = []
                self.active_tasks[i]['history'].append(history_entry)
                
                # Handle completion or failure
                if new_status_value == TaskStatus.COMPLETED.value:
                    self.active_tasks[i]['completed_at'] = datetime.now().isoformat()
                    self.stats["total_tasks_completed"] += 1
                    
                    # Process task completion (move to completed, handle dependencies)
                    self._handle_task_completion(task_id, self.active_tasks[i])
                elif new_status_value == TaskStatus.FAILED.value:
                    self.active_tasks[i]['failed_at'] = datetime.now().isoformat()
                    self.stats["total_tasks_failed"] += 1
                
                # Save changes
                self._save_all()
                logger.info(f"Updated task {task_id} status from {old_status} to {new_status_value}")
                return True
                
        logger.warning(f"Task {task_id} not found for status update")
        return False
        
    def _handle_task_completion(self, task_id: str, task: Dict[str, Any]):
        """Handle all side effects of task completion"""
        # Check for dependent tasks to unblock
        dependent_tasks = self.dependencies.get(task_id, [])
        for dep_id in dependent_tasks:
            for i, dep_task in enumerate(self.active_tasks):
                if dep_task.get('id') == dep_id:
                    # Remove the completed task from blockers
                    if task_id in dep_task.get('blockers', []):
                        self.active_tasks[i]['blockers'].remove(task_id)
                        
                    # Check if all blockers are now resolved
                    if not self.active_tasks[i]['blockers']:
                        # If previously blocked, update status to pending
                        if dep_task.get('status') == TaskStatus.BLOCKED.value:
                            self.active_tasks[i]['status'] = TaskStatus.PENDING.value
                            self.active_tasks[i]['updated_at'] = datetime.now().isoformat()
                            logger.info(f"Task {dep_id} unblocked by completion of {task_id}")
                            
        # Move task to completed list (remove from active)
        self.completed_tasks.append(task)
        self.active_tasks = [t for t in self.active_tasks if t.get('id') != task_id]
        
        # Add completion to history
        history_entry = {
            "id": f"history_{int(time.time())}_{uuid.uuid4().hex[:8]}",
            "task_id": task_id,
            "title": task.get('title'),
            "action": "completed",
            "timestamp": datetime.now().isoformat(),
            "details": task
        }
        self.task_history.append(history_entry)
        
    def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update task properties while maintaining version history
        
        Args:
            task_id: ID of the task to update
            updates: Dictionary of field updates
            
        Returns:
            True if successful, False otherwise
        """
        # Find task
        for i, task in enumerate(self.active_tasks):
            if task.get('id') == task_id:
                # Track history for each field
                if 'history' not in self.active_tasks[i]:
                    self.active_tasks[i]['history'] = []
                    
                for field, new_value in updates.items():
                    # Skip internal fields
                    if field in ['id', 'created_at', 'history', 'version']:
                        continue
                        
                    # Special handling for status field
                    if field == 'status':
                        self.update_task_status(task_id, new_value)
                        continue
                        
                    # Handle relationship fields
                    if field == 'dependencies':
                        self._update_dependencies(task_id, new_value)
                    elif field == 'blockers':
                        self._update_blockers(task_id, new_value)
                        
                    # Record history entry
                    old_value = task.get(field)
                    history_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "field": field,
                        "old_value": old_value,
                        "new_value": new_value
                    }
                    self.active_tasks[i]['history'].append(history_entry)
                    
                    # Update field
                    self.active_tasks[i][field] = new_value
                
                # Update version and timestamp
                self.active_tasks[i]['version'] += 1
                self.active_tasks[i]['updated_at'] = datetime.now().isoformat()
                
                # Save changes
                self._save_all()
                logger.info(f"Updated task {task_id} with {len(updates)} field changes")
                return True
                
        logger.warning(f"Task {task_id} not found for update")
        return False
        
    def _update_dependencies(self, task_id: str, new_dependencies: List[str]):
        """Update task dependencies and maintain relationship tracking"""
        # Get current dependencies
        task = next((t for t in self.active_tasks if t.get('id') == task_id), None)
        if not task:
            return
            
        old_dependencies = task.get('dependencies', [])
        
        # Remove task from old dependencies that are no longer present
        for old_dep in old_dependencies:
            if old_dep not in new_dependencies and old_dep in self.dependencies:
                if task_id in self.dependencies[old_dep]:
                    self.dependencies[old_dep].remove(task_id)
                    
        # Add task to new dependencies
        for new_dep in new_dependencies:
            if new_dep not in old_dependencies:
                if new_dep not in self.dependencies:
                    self.dependencies[new_dep] = []
                if task_id not in self.dependencies[new_dep]:
                    self.dependencies[new_dep].append(task_id)
                    
    def _update_blockers(self, task_id: str, new_blockers: List[str]):
        """Update task blockers and adjust task status accordingly"""
        # Update blockers relationship
        self.blockers[task_id] = new_blockers.copy()
        
        # Check if task should be blocked or unblocked
        if new_blockers:
            # Check if any blockers still exist and are not completed
            active_blockers = [b for b in new_blockers if 
                              any(t.get('id') == b and t.get('status') != TaskStatus.COMPLETED.value 
                                  for t in self.active_tasks + self.completed_tasks)]
                                  
            for i, task in enumerate(self.active_tasks):
                if task.get('id') == task_id:
                    if active_blockers and task.get('status') != TaskStatus.BLOCKED.value:
                        self.active_tasks[i]['status'] = TaskStatus.BLOCKED.value
                    elif not active_blockers and task.get('status') == TaskStatus.BLOCKED.value:
                        self.active_tasks[i]['status'] = TaskStatus.PENDING.value
        
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a task by ID, checking both active and completed tasks"""
        for task in self.active_tasks:
            if task.get('id') == task_id:
                return task.copy()
                
        for task in self.completed_tasks:
            if task.get('id') == task_id:
                return task.copy()
                
        return None
        
    def get_next_task(self, task_type: Optional[str] = None, 
                    tags: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """
        Get the next highest priority task, optionally filtered by type or tags
        
        Args:
            task_type: Optional task type filter
            tags: Optional list of tags to filter by (matching any tag)
            
        Returns:
            The next task or None if no tasks available
        """
        # Filter tasks by type and tags
        filtered_tasks = self.active_tasks
        
        if task_type:
            filtered_tasks = [t for t in filtered_tasks if t.get('type') == task_type]
            
        if tags:
            filtered_tasks = [t for t in filtered_tasks if any(tag in t.get('tags', []) for tag in tags)]
            
        # Filter out tasks that are blocked or not pending
        ready_tasks = [t for t in filtered_tasks if 
                      t.get('status') == TaskStatus.PENDING.value and 
                      len(t.get('blockers', [])) == 0]
                      
        if not ready_tasks:
            return None
            
        # Sort by priority (higher values first)
        ready_tasks.sort(key=lambda x: (x.get('priority', 0), x.get('created_at', '')), reverse=True)
        
        # Return the highest priority task
        return ready_tasks[0].copy() if ready_tasks else None
        
    def get_tasks_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get all tasks with a specific status"""
        try:
            status_value = TaskStatus[status].value if isinstance(status, str) else status
        except (KeyError, AttributeError):
            logger.error(f"Invalid task status: {status}")
            return []
            
        return [t.copy() for t in self.active_tasks if t.get('status') == status_value]
        
    def get_task_history(self, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get task history entries, optionally filtered by task ID
        
        Args:
            task_id: Optional task ID to filter by
            
        Returns:
            List of history entries
        """
        if task_id:
            return [h.copy() for h in self.task_history if h.get('task_id') == task_id]
        else:
            return [h.copy() for h in self.task_history]
            
    def delete_task(self, task_id: str) -> bool:
        """
        Delete a task by ID (moves to history with 'deleted' action)
        
        Args:
            task_id: ID of the task to delete
            
        Returns:
            True if successful, False otherwise
        """
        # Find and remove from active tasks
        task = next((t for t in self.active_tasks if t.get('id') == task_id), None)
        if task:
            self.active_tasks = [t for t in self.active_tasks if t.get('id') != task_id]
            
            # Create history entry
            history_entry = {
                "id": f"history_{int(time.time())}_{uuid.uuid4().hex[:8]}",
                "task_id": task_id,
                "title": task.get('title'),
                "action": "deleted",
                "timestamp": datetime.now().isoformat(),
                "details": task
            }
            self.task_history.append(history_entry)
            
            # Remove from relationships
            if task_id in self.dependencies:
                del self.dependencies[task_id]
            if task_id in self.blockers:
                del self.blockers[task_id]
                
            # Remove as a dependency for other tasks
            for dep_id, dependents in list(self.dependencies.items()):
                if task_id in dependents:
                    self.dependencies[dep_id] = [d for d in dependents if d != task_id]
                    
            # Remove as a blocker for other tasks
            for t_id, blockers in list(self.blockers.items()):
                if task_id in blockers:
                    self.blockers[t_id] = [b for b in blockers if b != task_id]
                    
            # Save changes
            self._save_all()
            logger.info(f"Deleted task {task_id}")
            return True
            
        logger.warning(f"Task {task_id} not found for deletion")
        return False
        
    def create_backup(self) -> str:
        """
        Create a timestamped backup of all task data
        
        Returns:
            Backup directory path
        """
        try:
            backup_dir = self.tasks_dir / f"backups/bk_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Save current state to backup
            self._save_json(backup_dir / "active_tasks.json", self.active_tasks)
            self._save_json(backup_dir / "completed_tasks.json", self.completed_tasks)
            self._save_json(backup_dir / "task_history.json", self.task_history)
            self._save_json(backup_dir / "recurring_tasks.json", self.recurring_tasks)
            self._save_json(backup_dir / "task_stats.json", self.stats)
            
            logger.info(f"Created task backup at {backup_dir}")
            return str(backup_dir)
        except Exception as e:
            logger.error(f"Error creating task backup: {e}")
            return ""
            
    def restore_from_backup(self, backup_path: str) -> bool:
        """
        Restore tasks from a backup
        
        Args:
            backup_path: Path to the backup directory
            
        Returns:
            True if successful, False otherwise
        """
        try:
            backup_dir = Path(backup_path)
            if not backup_dir.exists() or not backup_dir.is_dir():
                logger.error(f"Backup path {backup_path} not found or not a directory")
                return False
                
            # Load backup data
            active_tasks = self._load_json(backup_dir / "active_tasks.json", default=[])
            completed_tasks = self._load_json(backup_dir / "completed_tasks.json", default=[])
            task_history = self._load_json(backup_dir / "task_history.json", default=[])
            recurring_tasks = self._load_json(backup_dir / "recurring_tasks.json", default=[])
            
            # Backup current state before restoring
            current_backup = self.create_backup()
            
            # Restore data
            self.active_tasks = active_tasks
            self.completed_tasks = completed_tasks
            self.task_history = task_history
            self.recurring_tasks = recurring_tasks
            
            # Reinitialize relationships
            self._initialize_relationships()
            
            # Save restored state
            self._save_all()
            
            logger.info(f"Restored tasks from backup {backup_path} (previous state backed up to {current_backup})")
            return True
        except Exception as e:
            logger.error(f"Error restoring from backup: {e}")
            return False
            
    def get_stats(self) -> Dict[str, Any]:
        """Get task manager statistics"""
        self.stats.update({
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len(self.completed_tasks),
            "recurring_tasks": len(self.recurring_tasks),
            "history_entries": len(self.task_history)
        })
        return self.stats.copy()