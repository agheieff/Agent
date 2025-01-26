import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict

class TaskManager:
    PRIORITY_WEIGHTS = {
        'system': 3,
        'user': 2, 
        'maintenance': 1
    }

    def __init__(self, memory_path: Path):
        self.task_queue_path = memory_path / "tasks/queue.json"
        self.active_tasks = self._load_tasks()

    def _load_tasks(self) -> List[Dict]:
        if self.task_queue_path.exists():
            with open(self.task_queue_path) as f:
                return json.load(f)
        return []

    def add_task(self, task: Dict):
        """Add task with automatic prioritization"""
        task['type'] = task.get('type', 'maintenance')
        task['priority'] = self.PRIORITY_WEIGHTS.get(task.get('type', 'maintenance'), 1)
        self.active_tasks.append(task)
        self._save_tasks()

    def get_next_task(self) -> Optional[Dict]:
        """Get highest priority task"""
        if not self.active_tasks:
            return None
        return sorted(self.active_tasks, 
                     key=lambda x: x['priority'], 
                     reverse=True)[0]

    def _save_tasks(self):
        with open(self.task_queue_path, 'w') as f:
            json.dump(self.active_tasks, f, indent=2)
