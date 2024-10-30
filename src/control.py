import threading
import uuid

class ExecutionControl:
    def __init__(self):
        self.lock = threading.Lock()
        self.current_id = None

    def start_new(self):
        with self.lock:
            self.current_id = str(uuid.uuid4())
            return self.current_id

    def is_current(self, exec_id):
        with self.lock:
            return exec_id == self.current_id

    def stop_all(self):
        with self.lock:
            self.current_id = None

