"""Offline checks for endpoint identity roles; never grants or changes access."""


def role_evidence(assignments, principal, resource_scope, accepted_roles):
    """Container grants do not satisfy an account-level startup requirement.

    ARM Owner/Contributor alone do not grant Storage Blob data access. Conditional
    roles need separate review and must not be reported as unconditionally usable.
    """
    target = resource_scope.rstrip("/").lower()
    result = []
    for assignment in assignments:
        scope = str(assignment.get("scope") or "").rstrip("/").lower()
        if (assignment.get("principalId", "").lower() == principal.lower()
                and assignment.get("roleDefinitionName") in accepted_roles
                and scope and (target == scope or target.startswith(scope + "/"))):
            result.append({"role": assignment["roleDefinitionName"], "scope": assignment["scope"],
                           "condition": assignment.get("condition"), "id": assignment.get("id")})
    return {"verified_unconditional_role": any(not item["condition"] for item in result),
            "matching_assignments": result}
