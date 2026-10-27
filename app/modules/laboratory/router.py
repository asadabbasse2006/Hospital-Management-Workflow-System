from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


from app.modules.laboratory.schemas import ReleasedLabOrderRead
from app.modules.laboratory.service import get_released_results_for_doctor
from app.modules.laboratory.schemas import LabOrderActionResponse
from app.modules.laboratory.service import (
    verify_lab_results,
    release_lab_results,
)

from app.modules.laboratory.schemas import (
    LabResultsSubmit,
    LabResultsSubmitResponse,
    LabOrderQueueItem,
)

from app.modules.laboratory.service import (
    QUEUE_STATUSES,
    list_lab_orders,
    collect_specimen,
    start_lab_processing,
    submit_lab_results
)

from app.db.session import get_db
from app.modules.auth.dependencies import (
    get_current_user,
    require_csrf,
    require_roles,
)
from app.modules.laboratory.schemas import (
    LabOrderCreate,
    LabOrderRead,
    LabTestRead,
)
from app.modules.laboratory.service import (
    create_lab_order,
    list_active_tests,
)


router = APIRouter(
    prefix="/laboratory",
    tags=["Laboratory"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/tests",
    response_model=list[LabTestRead],
    dependencies=[
        Depends(
            require_roles(
                "Admin",
                "Doctor",
                "Lab Assistant",
                "Pathologist",
            )
        ),
    ],
)
def get_laboratory_tests(
    db: Session = Depends(get_db),
):
    return list_active_tests(db)


@router.post(
    "/orders",
    response_model=LabOrderRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_csrf),
        Depends(require_roles("Doctor")),
    ],
)
def order_laboratory_test(
    data: LabOrderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        result = create_lab_order(
            db,
            visit_id=data.visit_id.strip(),
            test_id=data.test_id,
            actor_user_id=current_user.id,
            clinical_notes=data.clinical_notes,
        )
        db.commit()
        return result

    except ValueError as exc:
        db.rollback()

        message = str(exc)
        if message == "Visit not found.":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        if message == "Active laboratory test not found.":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=message,
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The laboratory order could not be saved.",
        ) from exc



@router.get(
    "/orders",
    response_model=list[LabOrderQueueItem],
    dependencies=[
        Depends(require_roles("Lab Assistant", "Pathologist"))
    ],
)
def get_lab_order_queue(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role == "Lab Assistant":
        statuses = (
            "Ordered",
            "Specimen Collected",
            "In Progress",
        )
    elif current_user.role == "Pathologist":
        statuses = QUEUE_STATUSES
    else:
        # Defense in depth; require_roles should already reject this.
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to access the laboratory queue.",
        )

    return list_lab_orders(db, statuses=statuses)



@router.post(
    "/orders/{order_id}/collect",
    dependencies=[
        Depends(require_csrf),
        Depends(require_roles("Lab Assistant")),
    ],
)
def collect_lab_specimen(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        result = collect_specimen(
            db,
            order_id=order_id,
            actor_user_id=current_user.id,
        )
        db.commit()
        return result

    except ValueError as exc:
        db.rollback()
        message = str(exc)

        if message == "Laboratory order not found.":
            raise HTTPException(
                status_code=404,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=409,
            detail=message,
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Specimen collection could not be saved.",
        ) from exc


@router.post(
    "/orders/{order_id}/start",
    dependencies=[
        Depends(require_csrf),
        Depends(require_roles("Lab Assistant")),
    ],
)
def start_lab_order_processing(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        result = start_lab_processing(
            db,
            order_id=order_id,
            actor_user_id=current_user.id,
        )
        db.commit()
        return result

    except ValueError as exc:
        db.rollback()
        message = str(exc)

        if message == "Laboratory order not found.":
            raise HTTPException(
                status_code=404,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=409,
            detail=message,
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Laboratory processing could not be started.",
        ) from exc


@router.post(
    "/orders/{order_id}/results",
    response_model=LabResultsSubmitResponse,
    status_code=201,
    dependencies=[
        Depends(require_roles("Lab Assistant")),
        Depends(require_csrf),
    ],
)
def enter_lab_results(
    order_id: int,
    payload: LabResultsSubmit,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        result = submit_lab_results(
            db=db,
            order_id=order_id,
            actor_user_id=current_user.id,
            payload=payload,
        )
        db.commit()
        return result

    except Exception:
        db.rollback()
        raise

@router.post(
    "/orders/{order_id}/verify",
    response_model=LabOrderActionResponse,
    dependencies=[
        Depends(require_roles("Pathologist")),
        Depends(require_csrf),
    ],
)
def verify_results(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        result = verify_lab_results(
            db=db,
            order_id=order_id,
            actor_user_id=current_user.id,
        )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.post(
    "/orders/{order_id}/release",
    response_model=LabOrderActionResponse,
    dependencies=[
        Depends(require_roles("Pathologist")),
        Depends(require_csrf),
    ],
)
def release_results(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        result = release_lab_results(
            db=db,
            order_id=order_id,
            actor_user_id=current_user.id,
        )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise

@router.get(
    "/visits/{visit_business_id}/released-results",
    response_model=list[ReleasedLabOrderRead],
    dependencies=[Depends(require_roles("Doctor"))],
)
def get_doctor_released_lab_results(
    visit_business_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_released_results_for_doctor(
        db=db,
        visit_business_id=visit_business_id,
        doctor_user_id=current_user.id,
    )