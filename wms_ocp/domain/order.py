from __future__ import annotations
from decimal import Decimal
from typing import Any, List, Optional, Iterable

from .item import Item


class Order:
    def __init__(
        self,
        DeliveryOrder: int,
        Identifier: int,
        QuantityOfPalletsNeeded: Decimal = Decimal(0),
        QuantityOfPalletsNeededRounded: int = 0,
        AdditionalSpaces: int = 0,
        SupportPoint: str = "",
        MapNumber: str = "",
        LicensePlate: str = "",
        items: Optional[List[Item]] = None,
        # snake_case overrides
        delivery_order: Optional[int] = None,
        identifier: Optional[int] = None,
        quantity_of_pallets_needed: Optional[Decimal] = None,
        quantity_of_pallets_needed_rounded: Optional[int] = None,
        additional_spaces: Optional[int] = None,
        support_point: Optional[str] = None,
        map_number: Optional[str] = None,
        license_plate: Optional[str] = None,
    ):
        self._delivery_order = int(delivery_order) if delivery_order is not None else int(DeliveryOrder)
        self._identifier = int(identifier) if identifier is not None else int(Identifier)
        self._quantity_of_pallets_needed = Decimal(quantity_of_pallets_needed) if quantity_of_pallets_needed is not None else Decimal(QuantityOfPalletsNeeded)
        self._quantity_of_pallets_needed_rounded = int(quantity_of_pallets_needed_rounded) if quantity_of_pallets_needed_rounded is not None else int(QuantityOfPalletsNeededRounded)
        self._additional_spaces = int(additional_spaces) if additional_spaces is not None else int(AdditionalSpaces)
        self._support_point = support_point if support_point is not None else SupportPoint
        self._map_number = map_number if map_number is not None else MapNumber
        self._license_plate = license_plate if license_plate is not None else LicensePlate
        self._items: List[Item] = list(items) if items is not None else []

    # PascalCase properties for backward compatibility
    @property
    def DeliveryOrder(self) -> int:
        return self._delivery_order

    @DeliveryOrder.setter
    def DeliveryOrder(self, v: int):
        self._delivery_order = int(v)

    @property
    def Identifier(self) -> int:
        return self._identifier

    @Identifier.setter
    def Identifier(self, v: int):
        self._identifier = int(v)

    @property
    def QuantityOfPalletsNeeded(self) -> Decimal:
        return Decimal(self._quantity_of_pallets_needed)

    @QuantityOfPalletsNeeded.setter
    def QuantityOfPalletsNeeded(self, v: Decimal):
        self._quantity_of_pallets_needed = Decimal(v)

    @property
    def QuantityOfPalletsNeededRounded(self) -> int:
        return int(self._quantity_of_pallets_needed_rounded)

    @QuantityOfPalletsNeededRounded.setter
    def QuantityOfPalletsNeededRounded(self, v: int):
        self._quantity_of_pallets_needed_rounded = int(v)

    @property
    def AdditionalSpaces(self) -> int:
        return int(self._additional_spaces)

    @AdditionalSpaces.setter
    def AdditionalSpaces(self, v: int):
        self._additional_spaces = int(v)

    @property
    def SupportPoint(self) -> str:
        return self._support_point

    @SupportPoint.setter
    def SupportPoint(self, v: str):
        self._support_point = v

    @property
    def MapNumber(self) -> str:
        return self._map_number

    @MapNumber.setter
    def MapNumber(self, v: str):
        self._map_number = v

    @property
    def LicensePlate(self) -> str:
        return self._license_plate

    @LicensePlate.setter
    def LicensePlate(self, v: str):
        self._license_plate = v

    @property
    def Items(self) -> List[Any]:
        return list(self._items)

    @Items.setter
    def Items(self, items: List[Item]):
        self._items = list(items) if items is not None else []

    def SetItems(self, items: List[Item]):
        self._items = list(items)

    @property
    def Number(self):
        """Compatibilidade com C#: Number -> MapNumber"""
        return getattr(self, "MapNumber", None) or getattr(self, "map_number", None) or getattr(self, "number", None)

    @property
    def number(self):
        return self.Number
    
    # pythonic aliases for Order
    @property
    def delivery_order(self) -> int:
        return self.DeliveryOrder

    @delivery_order.setter
    def delivery_order(self, v: int):
        self.DeliveryOrder = v

    @property
    def identifier(self) -> int:
        return self.Identifier

    @identifier.setter
    def identifier(self, v: int):
        self.Identifier = v

    def set_items(self, items: List[Item]):
        return self.SetItems(items)

    def clone(self) -> "Order":
        return self.Clone()

    def set_quantity_of_pallets_needed(self, quantity_of_pallets_needed: Decimal):
        return self.SetQuantityOfPalletsNeeded(quantity_of_pallets_needed)

    def set_quantity_of_pallets_needed_rounded(self, q: int):
        return self.SetQuantityOfPalletsNeededRounded(q)

    def set_additional_spaces(self, additional_spaces: int):
        return self.SetAdditionalSpaces(additional_spaces)

    @property
    def items(self) -> List[Any]:
        """Pythonic alias expected by some rules: returns the order items list."""
        return self.Items

    @items.setter
    def items(self, value: Iterable[Item]):
        self.SetItems(list(value) if value is not None else [])

    def Clone(self) -> "Order":
        # Shallow clone: copy scalars and make a shallow copy of items list
        return Order(
            DeliveryOrder=self.DeliveryOrder,
            Identifier=self.Identifier,
            QuantityOfPalletsNeeded=Decimal(self.QuantityOfPalletsNeeded),
            QuantityOfPalletsNeededRounded=self.QuantityOfPalletsNeededRounded,
            AdditionalSpaces=self.AdditionalSpaces,
            SupportPoint=self.SupportPoint,
            MapNumber=self.MapNumber,
            LicensePlate=self.LicensePlate,
            _items=list(self._items),
        )

    def SetQuantityOfPalletsNeeded(self, quantityOfPalletsNeeded: Decimal):
        self.QuantityOfPalletsNeeded = Decimal(quantityOfPalletsNeeded)

    def SetQuantityOfPalletsNeededRounded(self, quantityOfPalletsNeededRounded: int):
        self.QuantityOfPalletsNeededRounded = quantityOfPalletsNeededRounded

    def SetAdditionalSpaces(self, aditionalSpaces: int):
        self.AdditionalSpaces = aditionalSpaces
    
    @property
    def quantity_of_pallets_needed(self) -> Decimal:
        return self.QuantityOfPalletsNeeded

    @quantity_of_pallets_needed.setter
    def quantity_of_pallets_needed(self, v: Decimal):
        self.QuantityOfPalletsNeeded = Decimal(v)

    @property
    def quantity_of_pallets_needed_rounded(self) -> int:
        return self.QuantityOfPalletsNeededRounded

    @quantity_of_pallets_needed_rounded.setter
    def quantity_of_pallets_needed_rounded(self, v: int):
        self.QuantityOfPalletsNeededRounded = int(v)

    @property
    def additional_spaces(self) -> int:
        return self.AdditionalSpaces

    @additional_spaces.setter
    def additional_spaces(self, v: int):
        self.AdditionalSpaces = int(v)

    @property
    def support_point(self) -> str:
        return self.SupportPoint

    @support_point.setter
    def support_point(self, v: str):
        self.SupportPoint = v

    @property
    def map_number(self) -> str:
        return self.MapNumber

    @map_number.setter
    def map_number(self, v: str):
        self.MapNumber = v

    @property
    def license_plate(self) -> str:
        return self.LicensePlate

    @license_plate.setter
    def license_plate(self, v: str):
        self.LicensePlate = v