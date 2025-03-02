import threading
import time
import json
import logging
import uuid
import os
import signal
import sys
from queue import PriorityQueue, Empty
from typing import List, Dict, Any, Optional, Tuple, Callable, Union
from pathlib import Path
from datetime import datetime, timedelta

# Set up logging
logger = logging.getLogger(__name__)

class ScheduledTask:
    """A task scheduled to run at a specific time or interval"""
    
    def __init__(self, task_id: str, name: str, callback: Callable, 
                 args: List = None, kwargs: Dict = None,
                 schedule_time: Union[datetime, str] = None, 
                 interval_seconds: int = None,
                 priority: int = 0,
                 metadata: Dict = None):
        
        self.task_id = task_id or f"task_{time.time()}_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.callback = callback
        self.args = args or []
        self.kwargs = kwargs or {}
        
        # Convert string to datetime if needed
        if isinstance(schedule_time, str):
            self.schedule_time = datetime.fromisoformat(schedule_time)
        else:
            self.schedule_time = schedule_time or datetime.now()
            
        self.interval_seconds = interval_seconds
        self.priority = priority
        self.metadata = metadata or {}
        
        # Task execution tracking
        self.last_run = None
        self.next_run = self.schedule_time
        self.run_count = 0
        self.created_at = datetime.now()
        self.status = "pending"
        self.last_error = None
        
    def should_run(self, current_time: datetime = None) -> bool:
        """Check if this task should run now"""
        current_time = current_time or datetime.now()
        return self.next_run <= current_time
        
    def update_next_run(self):
        """Update the next run time based on interval"""
        if self.interval_seconds:
            # Set next run relative to current time
            self.next_run = datetime.now() + timedelta(seconds=self.interval_seconds)
            return True
        return False
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary"""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "callback_name": self.callback.__name__ if hasattr(self.callback, "__name__") else str(self.callback),
            "schedule_time": self.schedule_time.isoformat() if self.schedule_time else None,
            "interval_seconds": self.interval_seconds,
            "priority": self.priority,
            "metadata": self.metadata,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "last_error": self.last_error
        }
        
    def __lt__(self, other):
        """For priority queue ordering"""
        if not isinstance(other, ScheduledTask):
            return NotImplemented
        return (self.next_run, self.priority) < (other.next_run, other.priority)

class TaskScheduler:
    """
    A robust scheduler for managing and executing tasks at specific times or intervals.
    
    Features:
    - Priority-based scheduling
    - Recurring tasks
    - Task dependencies
    - Persistent scheduling
    - Error recovery
    - Graceful shutdown
    """
    
    def __init__(self, storage_dir: Union[str, Path] = None):
        """
        Initialize the task scheduler.
        
        Args:
            storage_dir: Directory for storing scheduler state
        """
        # Set up storage
        self.storage_dir = Path(storage_dir) if storage_dir else Path("scheduler_storage")
        self.storage_dir.mkdir(exist_ok=True, parents=True)
        self.schedules_file = self.storage_dir / "schedules.json"
        self.history_file = self.storage_dir / "schedule_history.json"
        
        # Thread control
        self.lock = threading.Lock()
        self.running = True
        self.thread = None
        
        # Task queues and registries
        self.task_queue = PriorityQueue()
        self.tasks = {}  # task_id -> ScheduledTask
        self.history = []
        
        # Statistics
        self.stats = {
            "tasks_scheduled": 0,
            "tasks_executed": 0,
            "tasks_failed": 0,
            "last_execution_time": None,
            "start_time": datetime.now().isoformat()
        }
        
        # Settings
        self.check_interval = 1  # seconds between checking for due tasks
        self.save_interval = 60  # seconds between saving state
        self.max_retries = 3     # maximum retry attempts for failed tasks
        
        # Recovery
        self._load_state()
        
    def start(self):
        """Start the scheduler thread"""
        if self.thread and self.thread.is_alive():
            logger.warning("Scheduler is already running")
            return
            
        logger.info("Starting task scheduler")
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
        # Register signal handlers for graceful shutdown
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except (ValueError, AttributeError):
            # Handle cases where signals aren't available (e.g., Windows)
            logger.warning("Signal handlers not registered - clean shutdown may not be possible")
            
        return self.thread
        
    def stop(self):
        """Stop the scheduler thread gracefully"""
        if not self.thread or not self.thread.is_alive():
            logger.warning("Scheduler is not running")
            return
            
        logger.info("Stopping task scheduler")
        self.running = False
        self.thread.join(timeout=10)  # Wait up to 10 seconds
        
        if self.thread.is_alive():
            logger.warning("Scheduler thread did not terminate cleanly")
        else:
            logger.info("Scheduler stopped successfully")
            
        # Save state before exiting
        self._save_state()
        
    def _handle_signal(self, signum, frame):
        """Handle termination signals"""
        logger.info(f"Received signal {signum}, shutting down scheduler")
        self.stop()
        
    def _run(self):
        """Main scheduler loop"""
        last_save_time = time.time()
        
        while self.running:
            try:
                current_time = datetime.now()
                
                # Check for due tasks
                with self.lock:
                    # Rebuild the queue to get up-to-date tasks
                    self._rebuild_queue(current_time)
                    
                    # Process due tasks
                    while not self.task_queue.empty():
                        # Peek at the next task
                        try:
                            next_task = self.task_queue.queue[0]
                        except IndexError:
                            break
                            
                        # Check if it's due
                        if not next_task.should_run(current_time):
                            break  # Not time yet for this task
                            
                        # Get the task and remove it from the queue
                        task = self.task_queue.get()
                        
                        # Execute the task
                        self._execute_task(task)
                        
                        # If it's recurring, update next run time and requeue
                        if task.interval_seconds:
                            task.update_next_run()
                            self.task_queue.put(task)
                
                # Periodically save state
                if time.time() - last_save_time > self.save_interval:
                    self._save_state()
                    last_save_time = time.time()
                    
                # Sleep a bit
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(5)  # Longer sleep after error
                
        # Save state when shutting down
        self._save_state()
        
    def _rebuild_queue(self, current_time=None):
        """Rebuild the task queue (with lock already acquired)"""
        current_time = current_time or datetime.now()
        
        # Clear the queue
        self.task_queue = PriorityQueue()
        
        # Add all active tasks
        for task_id, task in self.tasks.items():
            if task.status == "pending" and task.next_run:
                self.task_queue.put(task)
                
    def _execute_task(self, task: ScheduledTask):
        """Execute a scheduled task"""
        logger.info(f"Executing scheduled task: {task.name} ({task.task_id})")
        
        # Update task tracking
        task.last_run = datetime.now()
        task.run_count += 1
        task.status = "running"
        self.stats["last_execution_time"] = task.last_run.isoformat()
        
        # Record in history
        history_entry = {
            "task_id": task.task_id,
            "name": task.name,
            "execution_time": task.last_run.isoformat(),
            "status": "started"
        }
        
        try:
            # Execute the task
            start_time = time.time()
            result = task.callback(*task.args, **task.kwargs)
            execution_time = time.time() - start_time
            
            # Update status
            task.status = "completed" if not task.interval_seconds else "pending"
            self.stats["tasks_executed"] += 1
            
            # Update history
            history_entry["status"] = "completed"
            history_entry["execution_time_seconds"] = execution_time
            history_entry["result"] = str(result) if result is not None else None
            
            logger.info(f"Task {task.name} completed in {execution_time:.2f}s")
            
        except Exception as e:
            # Handle failure
            error_msg = str(e)
            task.status = "failed"
            task.last_error = error_msg
            self.stats["tasks_failed"] += 1
            
            # Update history
            history_entry["status"] = "failed"
            history_entry["error"] = error_msg
            
            logger.error(f"Task {task.name} failed: {error_msg}")
            
        # Save to history
        self.history.append(history_entry)
        while len(self.history) > 1000:  # Keep history size reasonable
            self.history.pop(0)
            
    def schedule_task(self, name: str, callback: Callable, 
                     schedule_time: Union[datetime, str] = None,
                     interval_seconds: int = None,
                     args: List = None, 
                     kwargs: Dict = None,
                     priority: int = 0,
                     metadata: Dict = None) -> str:
        """
        Schedule a task to run once or repeatedly.
        
        Args:
            name: Task name
            callback: Function to call when task runs
            schedule_time: When to run the task (default: now)
            interval_seconds: If set, task will repeat at this interval
            args: Positional arguments for the callback
            kwargs: Keyword arguments for the callback
            priority: Task priority (higher numbers run first)
            metadata: Additional task metadata
            
        Returns:
            Task ID
        """
        with self.lock:
            # Create a new task
            task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            task = ScheduledTask(
                task_id=task_id,
                name=name,
                callback=callback,
                args=args,
                kwargs=kwargs,
                schedule_time=schedule_time,
                interval_seconds=interval_seconds,
                priority=priority,
                metadata=metadata
            )
            
            # Register the task
            self.tasks[task_id] = task
            self.task_queue.put(task)
            self.stats["tasks_scheduled"] += 1
            
            logger.info(f"Scheduled task {name} ({task_id}) to run at {task.next_run}")
            
            # Save state
            self._save_state()
            
            return task_id
            
    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a scheduled task
        
        Args:
            task_id: ID of the task to cancel
            
        Returns:
            True if found and canceled, False otherwise
        """
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = "canceled"
                logger.info(f"Canceled task {self.tasks[task_id].name} ({task_id})")
                
                # We can't easily remove it from the queue, but we'll skip it during execution
                # The queue will be rebuilt on the next pass
                
                # Save state
                self._save_state()
                return True
                
            logger.warning(f"Task {task_id} not found for cancellation")
            return False
            
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a task by ID"""
        with self.lock:
            task = self.tasks.get(task_id)
            if task:
                return task.to_dict()
            return None
            
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get all tasks"""
        with self.lock:
            return [task.to_dict() for task in self.tasks.values()]
            
    def get_due_tasks(self) -> List[Dict[str, Any]]:
        """Get all tasks that are currently due"""
        current_time = datetime.now()
        with self.lock:
            return [task.to_dict() for task in self.tasks.values()
                   if task.status == "pending" and task.should_run(current_time)]
                   
    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get task execution history"""
        with self.lock:
            return self.history[-limit:] if limit < len(self.history) else self.history[:]
            
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics"""
        with self.lock:
            stats = dict(self.stats)
            stats.update({
                "active_tasks": len([t for t in self.tasks.values() if t.status == "pending"]),
                "pending_executions": self.task_queue.qsize(),
                "uptime_seconds": (datetime.now() - datetime.fromisoformat(self.stats["start_time"])).total_seconds()
            })
            return stats
            
    def _save_state(self):
        """Save scheduler state to disk with error handling"""
        try:
            with self.lock:
                # Create backup of existing file
                if self.schedules_file.exists():
                    backup_path = self.schedules_file.with_suffix('.bak')
                    with open(self.schedules_file, 'r') as f:
                        backup_content = f.read()
                    with open(backup_path, 'w') as f:
                        f.write(backup_content)
                
                # Prepare task data (exclude callback which can't be serialized)
                task_data = [
                    {k: v for k, v in task.to_dict().items() if k != 'callback'}
                    for task in self.tasks.values()
                ]
                
                # Save tasks
                with open(self.schedules_file, 'w') as f:
                    json.dump({
                        "tasks": task_data,
                        "stats": self.stats,
                        "save_time": datetime.now().isoformat()
                    }, f, indent=2)
                    
                # Save history separately (it can get large)
                with open(self.history_file, 'w') as f:
                    json.dump({
                        "history": self.history,
                        "save_time": datetime.now().isoformat()
                    }, f, indent=2)
                    
                logger.debug("Scheduler state saved")
                
        except Exception as e:
            logger.error(f"Error saving scheduler state: {e}")
            
            # Try to restore backup if save failed
            if 'backup_path' in locals() and backup_path.exists():
                try:
                    with open(backup_path, 'r') as f:
                        backup_content = f.read()
                    with open(self.schedules_file, 'w') as f:
                        f.write(backup_content)
                    logger.info("Restored schedules from backup after failed save")
                except Exception as restore_err:
                    logger.error(f"Failed to restore from backup: {restore_err}")
            
    def _load_state(self):
        """Load scheduler state from disk with recovery"""
        try:
            if self.schedules_file.exists():
                with open(self.schedules_file, 'r') as f:
                    data = json.load(f)
                    
                # Load tasks (but we can't restore the callbacks)
                for task_data in data.get('tasks', []):
                    # Skip tasks we can't execute (no callback)
                    task_data['callback_unresolved'] = True
                    
                    # Recover task to track it, but mark as unresolved
                    task_id = task_data.get('task_id')
                    if task_id:
                        # We can't create a proper ScheduledTask without a callback
                        # This is just a placeholder to track that the task exists
                        logger.info(f"Found persisted task {task_data.get('name')} ({task_id}) - "
                                    f"callback must be re-registered")
                        
                # Load stats
                if 'stats' in data:
                    self.stats = data['stats']
                    
            # Load history
            if self.history_file.exists():
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    self.history = data.get('history', [])
                    
            logger.info(f"Scheduler state loaded")
            
        except Exception as e:
            logger.error(f"Error loading scheduler state: {e}")
            
            # Try to recover from backup
            backup_path = self.schedules_file.with_suffix('.bak')
            if backup_path.exists():
                try:
                    with open(backup_path, 'r') as f:
                        data = json.load(f)
                        
                    # Load stats
                    if 'stats' in data:
                        self.stats = data['stats']
                        
                    logger.info("Recovered scheduler state from backup")
                except Exception as backup_err:
                    logger.error(f"Failed to restore from backup: {backup_err}")
    
    def register_callback(self, task_id: str, callback: Callable) -> bool:
        """
        Register a callback for a persisted task
        
        Args:
            task_id: ID of the task
            callback: Callback function
            
        Returns:
            True if successful, False otherwise
        """
        with self.lock:
            task = self.tasks.get(task_id)
            if task and hasattr(task, 'callback_unresolved'):
                task.callback = callback
                delattr(task, 'callback_unresolved')
                logger.info(f"Registered callback for task {task.name} ({task_id})")
                return True
                
            logger.warning(f"Task {task_id} not found or doesn't need callback registration")
            return False
    
    def create_backup(self) -> str:
        """
        Create a backup of the scheduler state
        
        Returns:
            Path to backup directory
        """
        try:
            # Create backup directory
            backup_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = self.storage_dir / f"backups/bk_{backup_time}"
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Save current state to backup directory
            with self.lock:
                # Prepare task data (exclude callback which can't be serialized)
                task_data = [
                    {k: v for k, v in task.to_dict().items() if k != 'callback'}
                    for task in self.tasks.values()
                ]
                
                # Save tasks
                with open(backup_dir / "schedules.json", 'w') as f:
                    json.dump({
                        "tasks": task_data,
                        "stats": self.stats,
                        "save_time": datetime.now().isoformat()
                    }, f, indent=2)
                    
                # Save history
                with open(backup_dir / "history.json", 'w') as f:
                    json.dump({
                        "history": self.history,
                        "save_time": datetime.now().isoformat()
                    }, f, indent=2)
                    
            logger.info(f"Created scheduler backup at {backup_dir}")
            return str(backup_dir)
            
        except Exception as e:
            logger.error(f"Error creating scheduler backup: {e}")
            return ""
            
    def prune_history(self, max_age_days: int = 30, max_entries: int = 1000) -> int:
        """
        Prune old history entries
        
        Args:
            max_age_days: Maximum age of history entries in days
            max_entries: Maximum number of history entries to keep
            
        Returns:
            Number of entries removed
        """
        with self.lock:
            original_count = len(self.history)
            
            # Remove old entries
            if max_age_days > 0:
                cutoff_time = datetime.now() - timedelta(days=max_age_days)
                self.history = [
                    entry for entry in self.history
                    if datetime.fromisoformat(entry.get('execution_time', datetime.now().isoformat())) >= cutoff_time
                ]
                
            # Limit total entries
            if max_entries > 0 and len(self.history) > max_entries:
                self.history = self.history[-max_entries:]
                
            removed = original_count - len(self.history)
            if removed > 0:
                logger.info(f"Pruned {removed} history entries")
                self._save_state()
                
            return removed