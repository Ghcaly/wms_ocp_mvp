from __future__ import annotations
from typing import List, Optional, Any
from decimal import Decimal

from .pallet_setting import PalletSetting
from .container_type import ContainerType
from .packing_group import PackingGroup 
from .factor import Factor

class Product:
    def __init__(
        self,
        Code: int = 0,
        CodePromax: str = "",
        CodeBusinessUnit: str = "",
        Name: str = "",
        GrossWeight: Decimal = Decimal(0),
        LayerCode: int = 0,
        UnPalletized: bool = False,
        IsComplete: bool = True,
        Factor: Decimal = Decimal(0),
        BallastQuantity: Decimal = Decimal(0),
        TotalAreaOccupiedByUnit: Decimal = Decimal(0),
        TotalAreaOccupiedByBallast: Decimal = Decimal(0),
        CalculateAdditionalOccupation: bool = False,
        PackingGroup: PackingGroup = PackingGroup(),
        Factors: Optional[List[Factor]] = None,
        GroupAssociations: Optional[List[int]] = None,
        PalletSetting: PalletSetting = PalletSetting(),
        ContainerType: ContainerType = None,
        GroupAndSubGroup: int = 0,
        SupportPoint: str = "",
        ItemMarketplace: Any = None,

    ):
        # private backing fields (pythonic) - keep PascalCase properties for compatibility
        self._code = Code
        self._code_promax = CodePromax
        self._code_business_unit = CodeBusinessUnit
        self._name = Name
        self._gross_weight = Decimal(GrossWeight)
        self._layer_code = int(LayerCode)
        self._unpalletized = bool(UnPalletized)
        self._is_complete = bool(IsComplete)
        self._factor = Decimal(Factor)
        self._ballast_quantity = Decimal(BallastQuantity)
        self._total_area_occupied_by_unit = Decimal(TotalAreaOccupiedByUnit)
        self._total_area_occupied_by_ballast = Decimal(TotalAreaOccupiedByBallast)
        self._calculate_additional_occupation = bool(CalculateAdditionalOccupation)
        self._packing_group = PackingGroup
        self._factors = Factors or []
        self._group_associations = GroupAssociations or []
        self._pallet_setting = PalletSetting
        self._container_type = ContainerType
        self._group_and_sub_group = int(GroupAndSubGroup)
        self._support_point = SupportPoint
        self._item_marketplace = ItemMarketplace


    # --- backward-compatible PascalCase properties that map to private fields ---
    @property
    def Code(self):
        return self._code

    @Code.setter
    def Code(self, v):
        self._code = v

    @property
    def code(self):
        return self._code
    
    @property
    def CodePromax(self):
        return self._code_promax

    @CodePromax.setter
    def CodePromax(self, v):
        self._code_promax = v

    @property
    def CodeBusinessUnit(self):
        return self._code_business_unit

    @CodeBusinessUnit.setter
    def CodeBusinessUnit(self, v):
        self._code_business_unit = v

    @property
    def Name(self):
        return self._name

    @Name.setter
    def Name(self, v):
        self._name = v

    @property
    def GrossWeight(self):
        return self._gross_weight

    @GrossWeight.setter
    def GrossWeight(self, v):
        self._gross_weight = Decimal(v)

    @property
    def LayerCode(self):
        return self._layer_code

    @LayerCode.setter
    def LayerCode(self, v):
        self._layer_code = int(v)

    @property
    def UnPalletized(self):
        return self._unpalletized

    @UnPalletized.setter
    def UnPalletized(self, v):
        self._unpalletized = bool(v)

    @property
    def IsComplete(self):
        return self._is_complete

    @IsComplete.setter
    def IsComplete(self, v):
        self._is_complete = bool(v)

    @property
    def is_layer(self) -> bool:
        # lê a flag do pallet_setting (falso por padrão)
        return bool(self.PalletSetting.is_layer if self.PalletSetting else False)

    @property
    def Factor(self):
        return self._factor

    @Factor.setter
    def Factor(self, v):
        self._factor = Decimal(v)

    @property
    def ItemMarketplace(self):
        return self._item_marketplace

    @ItemMarketplace.setter
    def ItemMarketplace(self, v):
        self._item_marketplace = v

    @property
    def item_marketplace(self):
        """Pythonic snake_case alias for `ItemMarketplace`."""
        return self.ItemMarketplace

    @item_marketplace.setter
    def item_marketplace(self, v):
        self.ItemMarketplace = v
        
    @property
    def BallastQuantity(self):
        return self._ballast_quantity

    @BallastQuantity.setter
    def BallastQuantity(self, v):
        self._ballast_quantity = Decimal(v)

    @property
    def TotalAreaOccupiedByUnit(self):
        return self._total_area_occupied_by_unit

    @TotalAreaOccupiedByUnit.setter
    def TotalAreaOccupiedByUnit(self, v):
        self._total_area_occupied_by_unit = Decimal(v)

    @property
    def TotalAreaOccupiedByBallast(self):
        return self._total_area_occupied_by_ballast

    @TotalAreaOccupiedByBallast.setter
    def TotalAreaOccupiedByBallast(self, v):
        self._total_area_occupied_by_ballast = Decimal(v)

    @property
    def CalculateAdditionalOccupation(self):
        return self._calculate_additional_occupation

    @CalculateAdditionalOccupation.setter
    def CalculateAdditionalOccupation(self, v):
        self._calculate_additional_occupation = bool(v)

    @property
    def PackingGroup(self):
        return self._packing_group

    @PackingGroup.setter
    def PackingGroup(self, v):
        self._packing_group = v

    @property
    def Factors(self):
        return self._factors

    @Factors.setter
    def Factors(self, v):
        self._factors = v or []

    @property
    def GroupAssociations(self):
        return self._group_associations

    @GroupAssociations.setter
    def GroupAssociations(self, v):
        self._group_associations = v or []

    @property
    def PalletSetting(self):
        return self._pallet_setting

    @PalletSetting.setter
    def PalletSetting(self, v):
        self._pallet_setting = v

    @property
    def ContainerType(self):
        return self._container_type

    @ContainerType.setter
    def ContainerType(self, v):
        self._container_type = v

    @property
    def container_type(self) -> ContainerType:
        return self.ContainerType
    
    # @property
    # def GroupAndSubGroup(self):
    #     return self._group_and_sub_group

    @property
    def GroupAndSubGroup(self):
        return int(f"{self.PackingGroup.GroupCode}{self.PackingGroup.SubGroupCode}")
        
    # @GroupAndSubGroup.setter
    # def GroupAndSubGroup(self, v):
    #     self._group_and_sub_group = int(v)

    @property
    def SupportPoint(self):
        return self._support_point

    @SupportPoint.setter
    def SupportPoint(self, v):
        self._support_point = v

    @property
    def IsLayer(self) -> bool:
        return self.PalletSetting.is_layer if self.PalletSetting else False

    @property
    def is_layer(self) -> bool:
        return self.IsLayer

    # --- pythonic aliases (snake_case) --------------------------------
    @property
    def code(self):
        return self._code

    @code.setter
    def code(self, v):
        self._code = v

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, v):
        self._name = v

    @property
    def gross_weight(self):
        return self._gross_weight

    @gross_weight.setter
    def gross_weight(self, v):
        self._gross_weight = Decimal(v)

    # --- Properties that correspond to C# computed values ---
    @property
    def CanBePalletized(self) -> bool:
        # Faithful to C#: PackingGroup.IsValid && IsComplete && !UnPalletized
        return self.PackingGroup.IsValid and self.IsComplete and (not self.UnPalletized)

    # snake_case alias for Python callers
    @property
    def can_be_palletized(self) -> bool:
        return self.CanBePalletized

    # --- Methods mirroring the C# interface ---
    def CanBeAssociated(self, groupCode: int) -> bool:
        # C# likely checks group associations; simple membership check
        return groupCode in self.GroupAssociations

    # pythonic alias
    def can_be_associated(self, group_code: int) -> bool:
        return self.CanBeAssociated(group_code)

    def GetFactor(self, size: Any) -> Any:
        """
        Get factor by size. Raises exception if not found.
        Port of C# GetFactor method.
        """
        try:
            size_int = int(size)
        except (TypeError, ValueError):
            size_int = None

        for f in self.Factors:
            if size_int is not None:
                try:
                    if int(f.Size) == size_int:
                        return f
                except (TypeError, ValueError):
                    pass
            if f.Size == size or str(f.Size) == str(size):
                return f

        raise ValueError(
            f"Nao foi encontrado o fator de tamanho {size} para o item {self.CodePromax}. "
            f"Nome {self.Name}. Code: {self.Code}."
        )

    # pythonic alias
    def get_factor(self, size: Any) -> Any:
        return self.GetFactor(size)

    def GetQuantityOfLayerToSpace(self, spaceSize: Any, amount: int) -> int:
        # Port of C# semantics: return the number of units that form a layer in the given space
        # Implementation: if PalletSetting has QuantityDozen or Quantity, use it; otherwise fallback to amount
        if self.PalletSetting is not None:
            q = getattr(self.PalletSetting, 'QuantityDozen', None) or getattr(self.PalletSetting, 'Quantity', None)
            if q:
                try:
                    return int(q)
                except Exception:
                    pass
        # fallback: return amount (conservative)
        return int(amount)

    def get_quantity_of_layer_to_space(self, space_size: Any, amount: int) -> int:
        return self.GetQuantityOfLayerToSpace(space_size, amount)

    def SetFactors(self, factors: List[Any]):
        self.Factors = factors

    def SetGroupAssociations(self, groupsCanBeAssociated: List[int]):
        self.GroupAssociations = groupsCanBeAssociated

    def SetLayerCode(self, layerCode: int):
        self.LayerCode = int(layerCode)

    def SetPalletSetting(self, setting: Any):
        self.PalletSetting = setting

    def SetUnPalletized(self):
        self.UnPalletized = True

    def SetCalculateAdditionalOccupation(self, calculateAdditionalOccupation: bool, totalAreaOccupiedByUnit: Decimal, totalAreaOccupiedByBallast: Decimal):
        self.CalculateAdditionalOccupation = bool(calculateAdditionalOccupation)
        self.TotalAreaOccupiedByUnit = Decimal(totalAreaOccupiedByUnit)
        self.TotalAreaOccupiedByBallast = Decimal(totalAreaOccupiedByBallast)

    # --- UnitsPerBox compatibility (PascalCase + snake_case) ----------------
    @property
    def UnitsPerBox(self) -> int:
        """Backward-compatible PascalCase property for number of units per box.

        Default to 0 for products that are not package-type. Package subclass
        may override or set `_units_per_box`.
        """
        return int(getattr(self, '_units_per_box', 0) or 0)

    @UnitsPerBox.setter
    def UnitsPerBox(self, v):
        try:
            self._units_per_box = int(v)
        except Exception:
            self._units_per_box = 0

    @property
    def units_per_box(self) -> int:
        """Pythonic snake_case alias for `UnitsPerBox`."""
        return self.UnitsPerBox

    @units_per_box.setter
    def units_per_box(self, v):
        self.UnitsPerBox = v

    # --- lower-case aliases for Python code that may call them ---
    def set_factors(self, factors: List[Any]):
        self.SetFactors(factors)

    def set_group_associations(self, groups: List[int]):
        self.SetGroupAssociations(groups)

    def set_layer_code(self, layerCode: int):
        self.SetLayerCode(layerCode)

    def set_pallet_setting(self, setting: Any):
        self.SetPalletSetting(setting)

    def set_unpalletized(self):
        self.SetUnPalletized()

    def set_calculate_additional_occupation(self, calculateAdditionalOccupation: bool, totalAreaOccupiedByUnit: Decimal, totalAreaOccupiedByBallast: Decimal):
        self.SetCalculateAdditionalOccupation(calculateAdditionalOccupation, totalAreaOccupiedByUnit, totalAreaOccupiedByBallast)

    # --- Type checking helper methods ---
    def is_chopp(self) -> bool:
        """Check if product is Chopp type"""
        return self.ContainerType == ContainerType.CHOPP
    
    def not_chopp(self) -> bool:
        """Check if product is NOT marketplace type"""
        return not self.is_chopp()
    
    def NotChopp(self) -> bool:
        """Check if product is NOT marketplace type"""
        return self.not_chopp()
    
    def is_returnable(self) -> bool:
        """Check if product is Returnable type"""
        return self.ContainerType == ContainerType.RETURNABLE
    
    def is_disposable(self) -> bool:
        """Check if product is Disposable type"""
        return self.ContainerType == ContainerType.DISPOSABLE
    
    def IsDisposable(self) -> bool:
        """Check if product is Disposable type"""
        return self.is_disposable()
    
    def IsIsotonicWater(self) -> bool:
        """Check if product is IsotonicWater type"""
        return self.is_isotonic_water()
    
    def is_isotonic_water(self) -> bool:
        """Check if product is IsotonicWater type"""
        return self.ContainerType == ContainerType.ISOTONIC_WATER
    
    def is_package(self) -> bool:
        """Check if product is Package (Marketplace) type"""
        return self.ContainerType == ContainerType.PACKAGE
    
    def is_box_template(self) -> bool:
        """Check if product is BoxTemplate type"""
        return self.ContainerType == ContainerType.BOX_TEMPLATE
    
    def is_marketplace(self) -> bool:
        """Check if product is any marketplace type (Package or BoxTemplate)"""
        return self.is_package() or self.is_box_template()
    
    def not_marketplace(self) -> bool:
        """Check if product is NOT marketplace type"""
        return not self.is_marketplace()
    
    # PascalCase aliases for C# compatibility
    def IsChopp(self) -> bool:
        return self.is_chopp()
    
    def IsReturnable(self) -> bool:
        return self.is_returnable()
    
    def NotReturnable(self) -> bool:
        """Check if product is NOT returnable type"""
        return not self.is_returnable()
    
    def IsPackage(self) -> bool:
        return self.is_package()
    
    def IsBoxTemplate(self) -> bool:
        return self.is_box_template()
    
    def NotMarketplace(self) -> bool:
        return self.not_marketplace()
        
    def is_top_of_pallet(self) -> bool:
        """Check if product is TopOfPallet type"""
        return self.PalletSetting.IncludeTopOfPallet if self.PalletSetting else False
    
    def IsTopOfPallet(self) -> bool:
        """Check if product is TopOfPallet type"""
        return self.is_top_of_pallet()

    def mudar_tipo_produto(self, nova_classe, **atributos_extra):
        # Pega todos os atributos atuais
        atributos = self.__dict__.copy()
        # Atualiza com atributos extras (se houver)
        atributos.update(atributos_extra)
        # Cria um novo produto da nova classe
        return nova_classe(**atributos)
    

    @property
    def factors(self):
        return self._factors

    @factors.setter
    def factors(self, v):
        self._factors = v or []
    
class DisposableProduct(Product):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @property
    def ContainerType(self) -> ContainerType:
        return ContainerType.DISPOSABLE


class Chopp(Product):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @property
    def ContainerType(self) -> ContainerType:
        return ContainerType.CHOPP


class Returnable(Product):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @property
    def ContainerType(self) -> ContainerType:
        return ContainerType.RETURNABLE

class IsotonicWater(Product):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @property
    def ContainerType(self) -> ContainerType:
        return ContainerType.ISOTONIC_WATER

class Package(Product):
    def __init__(self, UnitsPerBox: int = 0, **kwargs):
        super().__init__(**kwargs)
        self._units_per_box = UnitsPerBox
    
    @property
    def UnitsPerBox(self) -> int:
        return self._units_per_box

    @UnitsPerBox.setter
    def UnitsPerBox(self, v):
        try:
            self._units_per_box = int(v)
        except Exception:
            self._units_per_box = 0
    
    @property
    def ContainerType(self) -> ContainerType:
        return ContainerType.PACKAGE

class BoxTemplate(Product):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._items_in_box = []
    
    @property
    def ItemsInBox(self):
        return self._items_in_box

    @ItemsInBox.setter
    def ItemsInBox(self, v):
        self._items_in_box = v or []

    @property
    def items_in_box(self):
        """Pythonic snake_case alias for `ItemsInBox`."""
        return self.ItemsInBox

    @items_in_box.setter
    def items_in_box(self, v):
        self.ItemsInBox = v
    
    @property
    def ContainerType(self) -> ContainerType:
        return ContainerType.BOX_TEMPLATE
