class DatabaseConnection:
    def __init__(self, connection_string: str = "sqlite:///hospital.db"):
        self.connection_string = connection_string

    def connect(self):
        return {"status": "connected", "connection_string": self.connection_string}
