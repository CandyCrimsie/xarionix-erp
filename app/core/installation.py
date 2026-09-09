from enum import StrEnum


class InstallationState(StrEnum):
    READY = "ready"
    INSTALLED = "installed"
    INCONSISTENT = "inconsistent"