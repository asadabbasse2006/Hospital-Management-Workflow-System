class LabService:
    def __init__(self):
        self._tests = {}

    def register_test(self, test):
        self._tests[test.test_id] = test
        return test

    def get_test(self, test_id: int):
        return self._tests.get(test_id)
