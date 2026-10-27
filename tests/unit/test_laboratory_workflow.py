
import pytest
from fastapi import HTTPException

from app.db.models import Department, Patient, Role, User, Visit
from app.db.laboratory_models import (
    LabOrder,
    LabOrderHistory,
    LabResult,
    LabTest,
)
from app.modules.laboratory.schemas import (
    LabResultItemCreate,
    LabResultsSubmit,
)
from app.modules.laboratory.service import (
    collect_specimen,
    create_lab_order,
    release_lab_results,
    start_lab_processing,
    submit_lab_results,
    verify_lab_results,
)


@pytest.fixture
def lab_context(db):
    doctor_role = Role(name="Doctor")
    assistant_role = Role(name="Lab Assistant")
    pathologist_role = Role(name="Pathologist")
    db.add_all([doctor_role, assistant_role, pathologist_role])
    db.flush()

    doctor = User(
        full_name="Test Doctor",
        username="test_doctor",
        password_hash="not-used-in-service-tests",
        role_id=doctor_role.id,
        is_active=True,
    )
    assistant = User(
        full_name="Test Lab Assistant",
        username="test_lab_assistant",
        password_hash="not-used-in-service-tests",
        role_id=assistant_role.id,
        is_active=True,
    )
    pathologist = User(
        full_name="Test Pathologist",
        username="test_pathologist",
        password_hash="not-used-in-service-tests",
        role_id=pathologist_role.id,
        is_active=True,
    )
    db.add_all([doctor, assistant, pathologist])
    db.flush()

    patient = Patient(
        patient_id="PAT-TEST-001",
        patient_name="Test Patient",
        phone="03000000001",
    )
    db.add(patient)
    db.flush()

    visit = Visit(
        visit_id="VIS-TEST-001",
        patient_id=patient.id,
        doctor_id=doctor.id,
        status="With Doctor",
        priority="Normal",
    )
    test = LabTest(
        code="CBC-TEST",
        name="Complete Blood Count",
        category="Hematology",
        specimen_type="Blood",
        is_active=True,
    )
    db.add_all([visit, test])
    db.flush()

    return {
        "doctor": doctor,
        "assistant": assistant,
        "pathologist": pathologist,
        "patient": patient,
        "visit": visit,
        "test": test,
    }


def create_order(db, lab_context):
    return create_lab_order(
        db,
        visit_id=lab_context["visit"].visit_id,
        test_id=lab_context["test"].id,
        actor_user_id=lab_context["doctor"].id,
    )


def valid_payload():
    return LabResultsSubmit(
        results=[
            LabResultItemCreate(
                analyte_code="HGB",
                analyte_name="Hemoglobin",
                result_value="13.5",
                unit="g/dL",
                reference_range="12.0-16.0",
            ),
            LabResultItemCreate(
                analyte_code="WBC",
                analyte_name="White Blood Cells",
                result_value="7.2",
                unit="10^9/L",
                reference_range="4.0-11.0",
            ),
        ]
    )


def move_to_in_progress(db, lab_context):
    order = create_order(db, lab_context)

    collect_specimen(
        db,
        order_id=order["id"],
        actor_user_id=lab_context["assistant"].id,
    )
    start_lab_processing(
        db,
        order_id=order["id"],
        actor_user_id=lab_context["assistant"].id,
    )
    return order["id"]


def test_create_order_starts_as_ordered(db, lab_context):
    result = create_order(db, lab_context)

    order = db.get(LabOrder, result["id"])
    assert order is not None
    assert order.status == "Ordered"

    history = db.query(LabOrderHistory).filter_by(
        order_id=order.id
    ).all()
    assert [item.action for item in history] == ["ORDER_CREATED"]


def test_specimen_cannot_be_collected_twice(db, lab_context):
    order = create_order(db, lab_context)
    actor_id = lab_context["assistant"].id

    collect_specimen(db, order_id=order["id"], actor_user_id=actor_id)

    with pytest.raises(ValueError, match="Only orders"):
        collect_specimen(db, order_id=order["id"], actor_user_id=actor_id)

    db.refresh(db.get(LabOrder, order["id"]))
    assert db.get(LabOrder, order["id"]).status == "Specimen Collected"


def test_processing_requires_collected_specimen(db, lab_context):
    order = create_order(db, lab_context)

    with pytest.raises(ValueError, match="collected specimen"):
        start_lab_processing(
            db,
            order_id=order["id"],
            actor_user_id=lab_context["assistant"].id,
        )

    assert db.get(LabOrder, order["id"]).status == "Ordered"


def test_results_require_in_progress_order(db, lab_context):
    order = create_order(db, lab_context)

    with pytest.raises(HTTPException) as exc:
        submit_lab_results(
            db=db,
            order_id=order["id"],
            actor_user_id=lab_context["assistant"].id,
            payload=valid_payload(),
        )

    assert exc.value.status_code == 409
    assert db.get(LabOrder, order["id"]).status == "Ordered"
    assert db.query(LabResult).filter_by(order_id=order["id"]).count() == 0


def test_duplicate_analytes_are_rejected_without_partial_results(
    db, lab_context
):
    order_id = move_to_in_progress(db, lab_context)

    duplicate_payload = LabResultsSubmit(
        results=[
            LabResultItemCreate(
                analyte_code="HGB",
                analyte_name="Hemoglobin",
                result_value="13.5",
            ),
            LabResultItemCreate(
                analyte_code="hgb",
                analyte_name="Hemoglobin",
                result_value="14.0",
            ),
        ]
    )

    with pytest.raises(HTTPException) as exc:
        submit_lab_results(
            db=db,
            order_id=order_id,
            actor_user_id=lab_context["assistant"].id,
            payload=duplicate_payload,
        )

    assert exc.value.status_code == 422
    assert db.get(LabOrder, order_id).status == "In Progress"
    assert db.query(LabResult).filter_by(order_id=order_id).count() == 0


def test_complete_workflow_requires_verification_before_release(
    db, lab_context
):
    order_id = move_to_in_progress(db, lab_context)

    submitted = submit_lab_results(
        db=db,
        order_id=order_id,
        actor_user_id=lab_context["assistant"].id,
        payload=valid_payload(),
    )
    assert submitted["status"] == "Pending Verification"
    assert len(submitted["results"]) == 2

    with pytest.raises(HTTPException) as exc:
        release_lab_results(
            db,
            order_id=order_id,
            actor_user_id=lab_context["pathologist"].id,
        )
    assert exc.value.status_code == 409

    verified = verify_lab_results(
        db,
        order_id=order_id,
        actor_user_id=lab_context["pathologist"].id,
    )
    assert verified["action"] == "RESULTS_VERIFIED"

    released = release_lab_results(
        db,
        order_id=order_id,
        actor_user_id=lab_context["pathologist"].id,
    )
    assert released["status"] == "Released"

    order = db.get(LabOrder, order_id)
    assert order.status == "Released"

    actions = [
        row.action
        for row in (
            db.query(LabOrderHistory)
            .filter_by(order_id=order_id)
            .order_by(LabOrderHistory.id)
            .all()
        )
    ]
    assert actions == [
        "ORDER_CREATED",
        "SPECIMEN_COLLECTED",
        "PROCESSING_STARTED",
        "RESULTS_SUBMITTED",
        "RESULTS_VERIFIED",
        "RESULTS_RELEASED",
    ]


def test_verification_cannot_be_recorded_twice(db, lab_context):
    order_id = move_to_in_progress(db, lab_context)

    submit_lab_results(
        db=db,
        order_id=order_id,
        actor_user_id=lab_context["assistant"].id,
        payload=valid_payload(),
    )

    verify_lab_results(
        db,
        order_id=order_id,
        actor_user_id=lab_context["pathologist"].id,
    )

    with pytest.raises(HTTPException) as exc:
        verify_lab_results(
            db,
            order_id=order_id,
            actor_user_id=lab_context["pathologist"].id,
        )

    assert exc.value.status_code == 409
