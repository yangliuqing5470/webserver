import os
import json
import threading


class DataBase():
    """数据库类.

    初步先写本地文件方式 (应该用mysql的)
    """
    def __init__(self, database_file_dirname):
        self.lock = threading.Lock()
        self.database_file = os.path.join(database_file_dirname, "database.json")

    def register(self, username, password):
        try:
            with self.lock:
                database = {}
                if os.path.exists(self.database_file):
                    with open(self.database_file, "r") as fp:
                        database = json.loads(fp.read())
                database[username] = password
                with open(self.database_file, "w") as fp:
                    fp.write(json.dumps(database))
            return True
        except Exception:
            return False

    def query(self, username):
        if not os.path.exists(self.database_file):
            return None
        with open(self.database_file, "r") as fp:
            database = json.loads(fp.read())
        if username in database:
            return database[username]
        return None
