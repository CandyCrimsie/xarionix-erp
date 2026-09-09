from enum import StrEnum


class InstallationState(StrEnum):
    READY = "ready"
    INSTALLED = "installed"
    INCONSISTENT = "inconsistent"


INSTALLATION_ADVISORY_LOCK_ID = (
    831_872_341
)