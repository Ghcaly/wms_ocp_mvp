from __future__ import annotations
from typing import Optional


class PalletSetting:
    def __init__(
        self,
        Quantity: int = 0,
        BulkPriority: int = 0,
        QuantityDozen: int = 0,
        QuantityBallast: int = 0,
        QuantityBallastMin: int = 0,
        Layers: int = 0,
        IncludeTopOfPallet: bool = False,
        BasePallet: bool = False,
        # optional snake_case overrides
        quantity: Optional[int] = None,
        bulk_priority: Optional[int] = None,
        quantity_dozen: Optional[int] = None,
        quantity_ballast: Optional[int] = None,
        quantity_ballast_min: Optional[int] = None,
        layers: Optional[int] = None,
        include_top_of_pallet: Optional[bool] = None,
        base_pallet: Optional[bool] = None,
    ):
        self._quantity = int(quantity) if quantity is not None else int(Quantity)
        self._bulk_priority = int(bulk_priority) if bulk_priority is not None else (int(BulkPriority) if BulkPriority is not None else None)
        self._quantity_dozen = int(quantity_dozen) if quantity_dozen is not None else (int(QuantityDozen) if QuantityDozen is not None else None)
        self._quantity_ballast = int(quantity_ballast) if quantity_ballast is not None else int(QuantityBallast)
        self._quantity_ballast_min = int(quantity_ballast_min) if quantity_ballast_min is not None else int(QuantityBallastMin)
        self._layers = int(layers) if layers is not None else int(Layers)
        self._include_top_of_pallet = bool(include_top_of_pallet) if include_top_of_pallet is not None else bool(IncludeTopOfPallet)
        self._base_pallet = bool(base_pallet) if base_pallet is not None else bool(BasePallet)

    # PascalCase properties (compat)
    @property
    def Quantity(self):
        return self._quantity

    @Quantity.setter
    def Quantity(self, v):
        self._quantity = int(v)

    @property
    def BulkPriority(self):
        return self._bulk_priority

    @BulkPriority.setter
    def BulkPriority(self, v):
        self._bulk_priority = int(v)

    @property
    def QuantityDozen(self):
        return self._quantity_dozen

    @QuantityDozen.setter
    def QuantityDozen(self, v):
        self._quantity_dozen = int(v)

    @property
    def QuantityBallast(self):
        return self._quantity_ballast

    @property
    def quantity_ballast(self):
        return self._quantity_ballast
    
    @QuantityBallast.setter
    def QuantityBallast(self, v):
        self._quantity_ballast = int(v)

    @property
    def Layers(self):
        return self._layers

    @Layers.setter
    def Layers(self, v):
        self._layers = int(v)

    @property
    def IncludeTopOfPallet(self):
        return self._include_top_of_pallet

    @IncludeTopOfPallet.setter
    def IncludeTopOfPallet(self, v: bool):
        self._include_top_of_pallet = bool(v)

    @property
    def BasePallet(self):
        return self._base_pallet

    @BasePallet.setter
    def BasePallet(self, v: bool):
        self._base_pallet = bool(v)

    # Pythonic aliases
    @property
    def quantity(self):
        return self._quantity

    @quantity.setter
    def quantity(self, v):
        self._quantity = int(v)

    @property
    def QuantityBallastMin(self) -> int:
        # tenta diversos nomes possíveis e fallback para atributo privado
        return self._quantity_ballast_min

    @QuantityBallastMin.setter
    def QuantityBallastMin(self, v: int):
        self._quantity_ballast_min = int(v)

    # snake_case alias
    @property
    def quantity_ballast_min(self) -> int:
        return self.QuantityBallastMin

    @quantity_ballast_min.setter
    def quantity_ballast_min(self, v: int):
        self.QuantityBallastMin = v

    def SetIncludeTopOfPallet(self, includeTopOfPallet: bool):
        self.IncludeTopOfPallet = includeTopOfPallet

    @classmethod
    def Build(cls, quantity: int, bulkPriority: int, quantityDozen: int, quantityBallast: int, layers: int, includeTopOfPallet: bool, basePallet: bool):
        return cls(
            Quantity=quantity,
            BulkPriority=bulkPriority,
            QuantityDozen=quantityDozen,
            QuantityBallast=quantityBallast,
            Layers=layers,
            IncludeTopOfPallet=includeTopOfPallet,
            BasePallet=basePallet,
        )

    @classmethod
    def build(cls, quantity: int, bulk_priority: int, quantity_dozen: int, quantity_ballast: int, layers: int, include_top_of_pallet: bool, base_pallet: bool):
        return cls.Build(quantity, bulk_priority, quantity_dozen, quantity_ballast, layers, include_top_of_pallet, base_pallet)

    @property
    def IsLayer(self) -> bool:
        # considera que ter Layers > 0 significa ser "layer"
        try:
            return bool(self._layers and int(self._layers) > 0)
        except Exception:
            return False

    @IsLayer.setter
    def IsLayer(self, value):
        # se setar True, garante pelo menos 1 layer; se setar False, zera layers
        if value:
            self._layers = max(1, int(value) if isinstance(value, int) else 1)
        else:
            self._layers = 0

    @property
    def is_layer(self) -> bool:
        return self.IsLayer

    @is_layer.setter
    def is_layer(self, value):
        self.IsLayer = value