class LabResultService:
    def __init__(self):
        self._results = {}

    def add_result(self, result):
        self._results[result.result_id] = result
        return result
