class DomainError(Exception):
    """Base exception for domain rule violations."""


class InvalidTransitionError(DomainError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"invalid order transition: {current} -> {target}")
        self.current = current
        self.target = target
