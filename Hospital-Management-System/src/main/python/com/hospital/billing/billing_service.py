class BillingService:
    def __init__(self):
        self._bills = {}

    def create_bill(self, bill):
        self._bills[bill.bill_id] = bill
        return bill

    def mark_paid(self, bill_id: int):
        bill = self._bills.get(bill_id)
        if bill is None:
            return {"status": "not_found"}
        bill.status = "paid"
        return {"status": "paid", "bill_id": bill_id}
