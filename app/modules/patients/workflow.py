
ALLOWED_TRANSITIONS = {
    "Receptionist": {
        "Receptionist": {"With Doctor"},
    },
    "Visits": {
        "Receptionist": {"With Doctor"},
    },
    "With Doctor": {
        "Doctor": {
            "Lab Tests",
            "Pharmacy",
            "Printing",
            "Completed",
        },
    },
    "Lab Tests": {
        "Lab Assistant": {"With Doctor"},
        "Pathologist": {"With Doctor"},
    },
    "Pharmacy": {
        "Pharmacy Assistant": {"Printing", "Completed"},
    },
    "Printing": {
        "Printing Assistant": {"Completed"},
    },
    "Completed": {},
}


def can_transition(
    current_status: str,
    role_name: str,
    target_status: str,
) -> bool:
    role_transitions = ALLOWED_TRANSITIONS.get(
        current_status, {}
    )
    allowed_targets = role_transitions.get(role_name, set())
    return target_status in allowed_targets
