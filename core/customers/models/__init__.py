"""Customer-модели shared DB."""

from core.customers.models.customer import Customer
from core.customers.models.customer_address import CustomerAddress
from core.customers.models.customer_identity import CustomerIdentity

__all__ = ["Customer", "CustomerAddress", "CustomerIdentity"]
