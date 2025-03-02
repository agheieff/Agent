import json
import logging
import uuid
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self, memory_path: Path):
        self.memory_path = memory_path
        self.tasks_dir = memory_path / "tasks"
        self.tasks_dir.mkdir(exist_ok=True, parents=True)
        self.active_tasks_path = self.tasks_dir / "active_tasks.json"
        self.completed_tasks_path = self.tasks_dir / "completed_tasks.json"
        self.history_path = self.tasks_dir / "task_history.json"
        self.recurring_tasks_path = self.tasks_dir / "recurring_tasks.json"
        self.active_tasks = self._load_json(self.active_tasks_path, default=[])
        self.completed_tasks = self._load_json(self.completed_tasks_path, default=[])
        self.task_history = self._load_json(self.history_path, default=[])
        self.recurring_tasks = self._load_json(self.recurring_tasks_path, default=[])
        self.dependencies = {}
        self.blockers = {}
        self._initialize_relationships()
        self.stats = {
            "total_tasks_created": 0,
            "total_tasks_completed": 0,
            "total_tasks_failed": 0,
            "total_modifications": 0,
            "last_backup_time": datetime.now().isoformat()
        }
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

    def _initialize_relationships(self):
        self.dependencies = {}
        self.blockers = {}
        for task in self.active_tasks:
            tid = task.get('id')
            if not tid:
                continue
            if tid not in self.dependencies:
                self.dependencies[tid] = []
            if tid not in self.blockers:
                self.blockers[tid] = []
            for dep_id in task.get('dependencies', []):
                if dep_id not in self.dependencies:
                    self.dependencies[dep_id] = []
                self.dependencies[dep_id].append(tid)
            for blocker_id in task.get('blockers', []):
                self.blockers[tid].append(blocker_id)

    def _recovery_check(self):
        try:
            logger.info("TaskManager recovery check")
            orphaned = set()
            for task_id in list(self.dependencies.keys()):
                if not self._task_exists(task_id) and self.dependencies[task_id]:
                    logger.warning(f"Orphaned deps for {task_id}")
                    orphaned.add(task_id)
            for task_id in orphaned:
                del self.dependencies[task_id]
            for task_id, blist in list(self.blockers.items()):
                if not self._task_exists(task_id):
                    logger.warning(f"Blockers for non-existent task {task_id}")
                    del self.blockers[task_id]
                else:
                    valid = [b for b in blist if self._task_exists(b)]
                    if len(valid) != len(blist):
                        logger.warning(f"Removed non-existent blockers for {task_id}")
                        self.blockers[task_id] = valid
            for i, task in enumerate(self.active_tasks):
                s = task.get('status')
                valid_status = ["pending","in_progress","completed","failed","blocked","scheduled","canceled","recurring"]
                if s not in valid_status:
                    logger.warning(f"Invalid status {s}, set to pending")
                    self.active_tasks[i]['status'] = "pending"
            self._save_all()
        except Exception as e:
            logger.error(f"Recovery error: {e}")

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

    def add_task(self, title: str, description: str, session_id: str = "", metadata: Dict[str, Any] = None,
                 task_id: str = None):
        if not task_id:
            task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        task = {
            "id": task_id,
            "title": title,
            "description": description,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "dependencies": [],
            "blockers": [],
            "tags": [],
            "metadata": metadata or {},
            "version": 1,
            "history": []
        }
        self.active_tasks.append(task)
        self.stats["total_tasks_created"] += 1
        self._save_all()
        logger.info(f"Added task: {task_id} - {title}")
        return task_id

    def add_subtask(self, parent_id: str, subtask_id: str, title: str, description: str, metadata: Dict[str, Any] = None):
        subtask = {
            "id": subtask_id,
            "title": title,
            "description": description,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "dependencies": [],
            "blockers": [],
            "tags": [],
            "metadata": metadata or {},
            "version": 1,
            "history": []
        }
        self.active_tasks.append(subtask)
        if parent_id not in self.dependencies:
            self.dependencies[parent_id] = []
        self.dependencies[parent_id].append(subtask_id)
        self.stats["total_tasks_created"] += 1
        self._save_all()
        logger.info(f"Added subtask {subtask_id} under {parent_id}")

    def update_task_status(self, task_id: str, new_status: str) -> bool:
        valid_status = ["pending","in_progress","completed","failed","blocked","scheduled","canceled","recurring"]
        if new_status not in valid_status:
            logger.error(f"Invalid status {new_status}")
            return False
        for i, t in enumerate(self.active_tasks):
            if t.get('id') == task_id:
                old_status = t.get('status')
                t['status'] = new_status
                t['updated_at'] = datetime.now().isoformat()
                t['version'] += 1
                if 'history' not in t:
                    t['history'] = []
                t['history'].append({
                    "timestamp": datetime.now().isoformat(),
                    "field": "status",
                    "old_value": old_status,
                    "new_value": new_status
                })
                if new_status == "completed":
                    t['completed_at'] = datetime.now().isoformat()
                    self.stats["total_tasks_completed"] += 1
                    self._handle_task_completion(task_id, t)
                elif new_status == "failed":
                    t['failed_at'] = datetime.now().isoformat()
                    self.stats["total_tasks_failed"] += 1
                self._save_all()
                logger.info(f"Task {task_id} status from {old_status} to {new_status}")
                return True
        logger.warning(f"Task {task_id} not found for update")
        return False

    def _handle_task_completion(self, task_id: str, task: Dict[str, Any]):
        dep_tasks = self.dependencies.get(task_id, [])
        for d_id in dep_tasks:
            for i, dep_task in enumerate(self.active_tasks):
                if dep_task.get('id') == d_id:
                    if task_id in dep_task.get('blockers', []):
                        self.active_tasks[i]['blockers'].remove(task_id)
                    if not self.active_tasks[i]['blockers'] and self.active_tasks[i]['status'] == "blocked":
                        self.active_tasks[i]['status'] = "pending"
                        self.active_tasks[i]['updated_at'] = datetime.now().isoformat()
        self.completed_tasks.append(task)
        self.active_tasks = [t for t in self.active_tasks if t.get('id') != task_id]
        history_entry = {
            "id": f"history_{int(time.time())}_{uuid.uuid4().hex[:8]}",
            "task_id": task_id,
            "title": task.get('title'),
            "action": "completed",
            "timestamp": datetime.now().isoformat(),
            "details": task
        }
        self.task_history.append(history_entry)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        for t in self.active_tasks:
            if t.get('id') == task_id:
                return t.copy()
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

    def get_stats(self) -> Dict[str, Any]:
        self.stats.update({
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len(self.completed_tasks),
            "recurring_tasks": len(self.recurring_tasks),
            "history_entries": len(self.task_history)
        })
        return self.stats.copy()
