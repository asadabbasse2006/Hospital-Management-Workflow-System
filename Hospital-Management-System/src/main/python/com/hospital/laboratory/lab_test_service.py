class LabTestService:
    def __init__(self):
        self._lab_tests = {}

    def add_lab_test(self, lab_test):
        self._lab_tests[lab_test.test_id] = lab_test
        return lab_test
