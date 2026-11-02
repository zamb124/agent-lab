"""Customer-модели shared DB."""

from core.customers.models.customer import Customer
from core.customers.models.customer_identity import CustomerIdentity

__all__ = ["Customer", "CustomerIdentity"]
