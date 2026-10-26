from datetime import datetime, timezone

from fastapi import HTTPException, status

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Visit, Patient
from app.db.laboratory_models import (
    LabOrder,
    LabOrderHistory,
    LabTest,
    LabResult
)

from app.modules.laboratory.schemas import LabResultsSubmit


def list_active_tests(db: Session) -> list[LabTest]:
    statement = (
        select(LabTest)
        .where(LabTest.is_active.is_(True))
        .order_by(LabTest.name.asc())
    )
    return list(db.scalars(statement).all())


def create_lab_order(
    db: Session,
    *,
    visit_id: str,
    test_id: int,
    actor_user_id: int,
    clinical_notes: str | None = None,
) -> dict:
    visit = db.scalar(
        select(Visit)
        .where(Visit.visit_id == visit_id)
        .with_for_update()
    )

    if visit is None or visit.doctor_id != actor_user_id:
        raise ValueError("Visit not found.")

    if visit.status != "With Doctor":
        raise ValueError(
            "A laboratory order can only be created while the visit "
            "is With Doctor."
        )

    test = db.scalar(
        select(LabTest).where(
            LabTest.id == test_id,
            LabTest.is_active.is_(True),
        )
    )

    if test is None:
        raise ValueError("Active laboratory test not found.")

    order = LabOrder(
        visit_pk=visit.id,
        test_id=test.id,
        ordered_by_user_id=actor_user_id,
        status="Ordered",
        clinical_notes=clinical_notes,
    )

    try:
        db.add(order)
        db.flush()

        db.add(
            LabOrderHistory(
                order_id=order.id,
                changed_by_user_id=actor_user_id,
                action="ORDER_CREATED",
                from_status=None,
                to_status="Ordered",
                reason="Laboratory order created.",
            )
        )
        db.flush()

        return {
            "id": order.id,
            "visit_id": visit.visit_id,
            "test_id": test.id,
            "test_code": test.code,
            "test_name": test.name,
            "status": order.status,
            "clinical_notes": order.clinical_notes,
            "created_at": order.created_at,
        }
    except Exception:
        db.rollback()
        raise


QUEUE_STATUSES = (
    "Ordered",
    "Specimen Collected",
    "In Progress",
    "Pending Verification",
)


def list_lab_orders(
    db: Session,
    *,
    statuses: tuple[str, ...] = QUEUE_STATUSES,
) -> list[dict]:
    statement = (
        select(LabOrder, LabTest, Visit, Patient)
        .join(LabTest, LabOrder.test_id == LabTest.id)
        .join(Visit, LabOrder.visit_pk == Visit.id)
        .join(Patient, Visit.patient_id == Patient.id)
        .where(LabOrder.status.in_(statuses))
        .order_by(LabOrder.created_at.asc(), LabOrder.id.asc())
    )

    rows = db.execute(statement).all()

    return [
        {
            "id": order.id,
            "visit_id": visit.visit_id,
            "patient_id": patient.patient_id,
            "patient_name": patient.patient_name,
            "test_id": test.id,
            "test_code": test.code,
            "test_name": test.name,
            "specimen_type": test.specimen_type,
            "status": order.status,
            "created_at": order.created_at,
            "specimen_collected_at": order.specimen_collected_at,
            "started_at": order.started_at,
        }
        for order, test, visit, patient in rows
    ]


def collect_specimen(
    db: Session,
    *,
    order_id: int,
    actor_user_id: int,
) -> dict:
    order = db.scalar(
        select(LabOrder)
        .where(LabOrder.id == order_id)
        .with_for_update()
    )

    if order is None:
        raise ValueError("Laboratory order not found.")

    if order.status != "Ordered":
        raise ValueError(
            "Only orders with status Ordered can be collected."
        )

    now = datetime.now(timezone.utc)

    order.status = "Specimen Collected"
    order.specimen_collected_at = now
    order.specimen_collected_by_user_id = actor_user_id
    order.updated_at = now

    db.add(
        LabOrderHistory(
            order_id=order.id,
            changed_by_user_id=actor_user_id,
            action="SPECIMEN_COLLECTED",
            from_status="Ordered",
            to_status="Specimen Collected",
            reason="Specimen collection recorded.",
        )
    )

    db.flush()

    return {
        "id": order.id,
        "status": order.status,
        "specimen_collected_at": order.specimen_collected_at,
    }

def start_lab_processing(
    db: Session,
    *,
    order_id: int,
    actor_user_id: int,
) -> dict:
    order = db.scalar(
        select(LabOrder)
        .where(LabOrder.id == order_id)
        .with_for_update()
    )

    if order is None:
        raise ValueError("Laboratory order not found.")

    if order.status != "Specimen Collected":
        raise ValueError(
            "Only orders with a collected specimen can begin processing."
        )

    now = datetime.now(timezone.utc)

    order.status = "In Progress"
    order.started_at = now
    order.updated_at = now

    db.add(
        LabOrderHistory(
            order_id=order.id,
            changed_by_user_id=actor_user_id,
            action="PROCESSING_STARTED",
            from_status="Specimen Collected",
            to_status="In Progress",
            reason="Laboratory processing started.",
        )
    )

    db.flush()

    return {
        "id": order.id,
        "status": order.status,
        "started_at": order.started_at,
    }


def submit_lab_results(
    db: Session,
    order_id: int,
    actor_user_id: int,
    payload: LabResultsSubmit,
) -> dict:
    """
    Save a complete result batch and move the order to Pending Verification.

    The caller owns the transaction and must commit or roll back.
    """

    # Lock the order to prevent concurrent submissions or status changes.
    order = db.scalar(
        select(LabOrder)
        .where(LabOrder.id == order_id)
        .with_for_update()
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Laboratory order not found.",
        )

    if order.status != "In Progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Results can only be submitted for orders "
                "that are In Progress."
            ),
        )

    # Reject duplicate analytes within the submitted batch.
    codes = [item.analyte_code.strip().casefold() for item in payload.results]

    if any(not code for code in codes):
        raise HTTPException(
            status_code=422,
            detail="Analyte codes cannot be empty.",
        )

    if len(codes) != len(set(codes)):
        raise HTTPException(
            status_code=422,
            detail="The submitted batch contains duplicate analyte codes.",
        )

    # Prevent duplicate analytes already saved for this order.
    existing_codes = db.scalars(
        select(LabResult.analyte_code).where(
            LabResult.order_id == order.id
        )
    ).all()

    existing_codes_normalized = {
        code.strip().casefold() for code in existing_codes
    }

    if existing_codes_normalized.intersection(codes):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "One or more analytes already have results for this order. "
                "No results were submitted."
            ),
        )

    created_results = []

    for item in payload.results:
        analyte_code = item.analyte_code.strip()
        analyte_name = item.analyte_name.strip()
        result_value = item.result_value.strip()

        if not analyte_name or not result_value:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Analyte name and result value cannot be empty."
                ),
            )

        result = LabResult(
            order_id=order.id,
            analyte_code=analyte_code,
            analyte_name=analyte_name,
            result_value=result_value,
            unit=item.unit.strip() if item.unit else None,
            reference_range=(
                item.reference_range.strip()
                if item.reference_range
                else None
            ),
            abnormal_flag=item.abnormal_flag,
            notes=item.notes.strip() if item.notes else None,
            entered_by_user_id=actor_user_id,
        )

        db.add(result)
        created_results.append(result)

    # The batch is complete and ready for Pathologist review.
    order.status = "Pending Verification"

    db.add(
        LabOrderHistory(
            order_id=order.id,
            changed_by_user_id=actor_user_id,
            action="RESULTS_SUBMITTED",
            from_status="In Progress",
            to_status="Pending Verification",
            reason=f"Submitted {len(created_results)} analyte result(s).",
        )
    )

    db.flush()

    return {
        "order_id": order.id,
        "status": order.status,
        "results": created_results,
    }

def verify_lab_results(
    db: Session,
    order_id: int,
    actor_user_id: int,
) -> dict:
    """Record Pathologist verification of a complete submitted result batch."""

    order = db.scalar(
        select(LabOrder)
        .where(LabOrder.id == order_id)
        .with_for_update()
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Laboratory order not found.",
        )

    if order.status != "Pending Verification":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only orders pending verification can be verified.",
        )

    result_count = db.scalar(
        select(LabResult.id)
        .where(LabResult.order_id == order.id)
        .limit(1)
    )

    if result_count is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot verify an order without results.",
        )

    already_verified = db.scalar(
        select(LabOrderHistory.id)
        .where(
            LabOrderHistory.order_id == order.id,
            LabOrderHistory.action == "RESULTS_VERIFIED",
        )
        .limit(1)
    )

    if already_verified is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This result batch has already been verified.",
        )

    db.add(
        LabOrderHistory(
            order_id=order.id,
            changed_by_user_id=actor_user_id,
            action="RESULTS_VERIFIED",
            from_status=order.status,
            to_status=order.status,
            reason="Result batch verified by Pathologist.",
        )
    )

    db.flush()

    return {
        "order_id": order.id,
        "status": order.status,
        "action": "RESULTS_VERIFIED",
        "message": "Results verified. The report is ready for release.",
    }


def release_lab_results(
    db: Session,
    order_id: int,
    actor_user_id: int,
) -> dict:
    """Release a result batch after explicit Pathologist verification."""

    order = db.scalar(
        select(LabOrder)
        .where(LabOrder.id == order_id)
        .with_for_update()
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Laboratory order not found.",
        )

    if order.status != "Pending Verification":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only verified, unreleased orders can be released.",
        )

    verification = db.scalar(
        select(LabOrderHistory.id)
        .where(
            LabOrderHistory.order_id == order.id,
            LabOrderHistory.action == "RESULTS_VERIFIED",
        )
        .limit(1)
    )

    if verification is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The result batch must be verified before release.",
        )

    result_count = db.scalar(
        select(LabResult.id)
        .where(LabResult.order_id == order.id)
        .limit(1)
    )

    if result_count is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot release an order without results.",
        )

    previous_status = order.status
    order.status = "Released"

    db.add(
        LabOrderHistory(
            order_id=order.id,
            changed_by_user_id=actor_user_id,
            action="RESULTS_RELEASED",
            from_status=previous_status,
            to_status="Released",
            reason="Verified laboratory report released by Pathologist.",
        )
    )

    db.flush()

    return {
        "order_id": order.id,
        "status": order.status,
        "action": "RESULTS_RELEASED",
        "message": "Laboratory report released successfully.",
    }

def get_released_results_for_doctor(
    db: Session,
    visit_business_id: str,
    doctor_user_id: int,
) -> list[dict]:
    """
    Return released laboratory results for a visit assigned to this doctor.
    """

    # Confirm that this visit belongs to the authenticated doctor.
    visit = db.scalar(
        select(Visit).where(
            Visit.visit_id == visit_business_id,
            Visit.doctor_id == doctor_user_id,
        )
    )

    if visit is None:
        # Use 404 for both nonexistent visits and visits not assigned
        # to this doctor, avoiding disclosure of another doctor's visits.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visit not found.",
        )

    # Only released orders are eligible for doctor-facing access.
    order_rows = db.execute(
        select(LabOrder, LabTest)
        .join(LabTest, LabOrder.test_id == LabTest.id)
        .where(
            LabOrder.visit_pk == visit.id,
            LabOrder.status == "Released",
        )
        .order_by(LabOrder.created_at.desc(), LabOrder.id.desc())
    ).all()

    released_orders = []

    for order, test in order_rows:
        result_rows = db.scalars(
            select(LabResult)
            .where(LabResult.order_id == order.id)
            .order_by(LabResult.id)
        ).all()

        released_orders.append(
            {
                "order_id": order.id,
                "visit_id": visit.visit_id,
                "test_id": test.id,
                "test_code": test.code,
                "test_name": test.name,
                "status": order.status,
                "created_at": order.created_at,
                "results": result_rows,
            }
        )

    return released_orders