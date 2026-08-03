"""Domain errors for the orders service."""


class OrderError(Exception):
    """Base class for all order errors."""


class OrderNotFound(OrderError):
    """Raised when an order id does not exist."""


class InvalidTransition(OrderError):
    """Raised when an order status change is not allowed."""


class AuthError(OrderError):
    """Raised when a request is not authenticated or authorized."""
