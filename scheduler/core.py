|
import threading
import time
import json
from datetime import datetime
class TaskScheduler:
def __init__(self, storage_file="schedules.json"):
self.storage_file = storage_file
self.lock = threading.Lock()
self.schedules = self._load_schedules()
self.running = True
self.thread = threading.Thread(target=self._run)
self.thread.daemon = True
def _load_schedules(self):