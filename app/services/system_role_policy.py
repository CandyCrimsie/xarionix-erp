from models.roles import Role


class SystemRoleProtectedError(
    Exception
):
    def __init__(
        self,
        *,
        role_id: int,
        system_key: str | None,
    ) -> None:
        self.role_id = role_id
        self.system_key = system_key

        super().__init__(
            "System role is managed by the system"
        )


def ensure_role_is_mutable(
    role: Role,
) -> None:
    if role.is_system:
        raise SystemRoleProtectedError(
            role_id=role.id,
            system_key=role.system_key,
        )