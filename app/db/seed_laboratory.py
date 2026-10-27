
from sqlalchemy import select

from app.db.session import SessionLocal
from app.db.laboratory_models import LabTest


INITIAL_TESTS = [
    {
        "code": "CBC",
        "name": "Complete Blood Count",
        "category": "Hematology",
        "specimen_type": "EDTA blood",
        "description": "Development catalog entry.",
    },
    {
        "code": "GLUCOSE",
        "name": "Blood Glucose",
        "category": "Biochemistry",
        "specimen_type": "Blood",
        "description": "Development catalog entry.",
    },
    {
        "code": "URINALYSIS",
        "name": "Urinalysis",
        "category": "Clinical Pathology",
        "specimen_type": "Urine",
        "description": "Development catalog entry.",
    },
]


def seed_laboratory_tests() -> None:
    with SessionLocal() as db:
        try:
            for item in INITIAL_TESTS:
                existing = db.scalar(
                    select(LabTest).where(LabTest.code == item["code"])
                )

                if existing is None:
                    db.add(LabTest(**item))
                    print(f"Added: {item['code']}")
                else:
                    print(f"Already exists: {item['code']}")

            db.commit()
            print("Laboratory catalog seeding completed.")

        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    seed_laboratory_tests()
