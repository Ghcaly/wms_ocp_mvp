from __future__ import annotations
from decimal import Decimal
from typing import Optional, Any
import numpy as np


class Factor:
    """Pythonic Factor with private backing fields.

    Backwards-compatible properties (PascalCase) are provided so migrated code
    that expects `Factor.Size` / `Factor.Value` / `Factor.Quantity` continues to work.
    The constructor accepts either PascalCase or snake_case argument names.
    """

    def __init__(self, Size: Any = None, Value: Decimal = None, Quantity: Optional[int] = None, HasQuantity: Optional[bool] = None, *, size: Any = None, value: Decimal = None, quantity: Optional[int] = None, has_quantity: Optional[bool] = None):
        # support both naming conventions: snake_case overrides PascalCase when provided
        resolved_size = size if size is not None else Size
        resolved_value = value if value is not None else Value
        resolved_quantity = quantity if quantity is not None else Quantity
        resolved_has_quantity = has_quantity if has_quantity is not None else HasQuantity

        self._size: Any = resolved_size
        self._value: Optional[Decimal] = Decimal(resolved_value) if resolved_value is not None else None
        self._quantity: Optional[int] = int(resolved_quantity) if resolved_quantity is not None and not np.isnan(resolved_quantity) else None
        self._has_quantity: bool = resolved_has_quantity if resolved_has_quantity is not None else (self._quantity is not None and self._quantity > 0)

    # PascalCase properties (compat)
    @property
    def Size(self) -> Any:
        return self._size

    @Size.setter
    def Size(self, v: Any):
        self._size = v

    @property
    def Value(self) -> Optional[Decimal]:
        return self._value

    @Value.setter
    def Value(self, v: Decimal):
        self._value = Decimal(v) if v is not None else None

    @property
    def Quantity(self) -> Optional[int]:
        return self._quantity

    @Quantity.setter
    def Quantity(self, v: Optional[int]):
        self._quantity = int(v) if v is not None else None

    @property
    def HasQuantity(self) -> bool:
        return self._has_quantity

    @HasQuantity.setter
    def HasQuantity(self, v: bool):
        self._has_quantity = bool(v)

    # pythonic aliases
    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, v):
        self._size = v

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        self._value = Decimal(v) if v is not None else None

    @property
    def quantity(self):
        return self._quantity

    @quantity.setter
    def quantity(self, q):
        self._quantity = int(q) if q is not None else None

    @property
    def has_quantity(self) -> bool:
        return self._has_quantity

    @has_quantity.setter
    def has_quantity(self, v: bool):
        self._has_quantity = bool(v)
