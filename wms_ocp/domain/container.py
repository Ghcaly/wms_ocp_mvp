from __future__ import annotations
# ...existing code...
from typing import List, Optional, Any, Tuple
from copy import deepcopy
# from ..adapters.logger_instance import logger
from ..domain.container_type import ContainerType

class Container:
    """
    Python port of C# IContainer / Container interface.

    - Exposes properties and methods used by rules:
      Products, ProductBase, AddMountedProduct, IncreaseAssemblySequence, SetProductBase,
      IsTypeBaseChopp/WaterIsotonic/Returnable/Disposable, GroupAndSubGroup, Blocked, Block, Clear,
      RemoveMountedProduct, DifferentPackingGroupQuantity, Clone, DifferentProductTypeQuantity,
      DifferentPackingCodeQuantity.
    """

    def __init__(self, product_base: Optional[Any] = None, products: Optional[List[Any]] = None):
        # private backing fields (pythonic naming)
        self._products: List[Any] = products or []
        self._product_base: Optional[Any] = product_base
        self._blocked: bool = False
        self._assembly_sequence_counter: int = 0
        self._group_and_subgroup: int = 0
        self._layer: bool = False
        self._keg_exclusive: bool = False
        self._bulk: bool = False
        self._occupation: int = 0
        self._weight: int = 0

    @property
    def Products(self) -> Tuple[Any, ...]:
        return tuple(self._products)

    @property
    def ProductBase(self) -> Optional[Any]:
        return getattr(self, "_product_base", None)

    # @property
    # def Remount(self):
    #     products = self._products

    #     has_returnable = any(p.Product.is_returnable() for p in products)

    #     has_non_returnable_or_special = any(
    #         (not p.Product.is_returnable())
    #         or p.Product.is_isotonic_water()
    #         or p.Product.is_chopp()
    #         for p in products
    #     )

    #     return has_returnable and has_non_returnable_or_special

    # @property
    # def Remount(self) -> bool:
    #     """Faithful port of C# Pallet.Remount:

    #     True when there's at least one returnable product and at least one
    #     product that is either not returnable or is isotonic water or is chopp.
    #     """
    #     has_returnable = False
    #     has_other = False
    #     for p in self._products:
    #         prod = getattr(p, 'Product', getattr(p, 'product', None))
    #         if prod is None:
    #             continue

    #         is_returnable = bool(getattr(prod, 'is_returnable', getattr(prod, 'IsReturnable', False)))
    #         is_isotonic = bool(getattr(prod, 'is_isotonic_water', getattr(prod, 'IsIsotonicWater', False)))
    #         is_chopp = bool(getattr(prod, 'is_chopp', getattr(prod, 'IsChopp', False)))

    #         if is_returnable:
    #             has_returnable = True

    #         if (not is_returnable) or is_isotonic or is_chopp:
    #             has_other = True

    #         if has_returnable and has_other:
    #             return True

    #     return False

    @property
    def Remount(self) -> bool:
        # Normaliza para sempre pegar o produto correto
        products = [p.Product if hasattr(p, "Product") else p for p in self._products]

        has_returnable = any(p.is_returnable() for p in products)
        has_other = any((not p.is_returnable()) or p.is_isotonic_water() or p.is_chopp() for p in products)

        return has_returnable and has_other

    @property
    def remount(self) -> bool:
        return self.Remount
    
    @ProductBase.setter
    def ProductBase(self, value: Any):
        self._product_base = value

    def AddMountedProduct(self, mounted_product: Any, amount: Optional[int] = None, package: Optional[int] = None):
        if amount is not None:
            if hasattr(mounted_product, "Amount"):
                mounted_product.Amount = amount
            else:
                setattr(mounted_product, "Amount", amount)

        if package is not None:
            setattr(mounted_product, "Package", package)

        if mounted_product not in self._products:
            # logger.add_execution_log(f"Adicionando produto montado {mounted_product.Product.name} ao container")
            self._products.append(mounted_product)

    def IncreaseAssemblySequence(self, mounted_product: Any):
        self._assembly_sequence_counter += 1
        try:
            mounted_product.AssemblySequence = self._assembly_sequence_counter
        except Exception:
            setattr(mounted_product, "AssemblySequence", self._assembly_sequence_counter)

    def SetProductBase(self, product: Any):
        # set private backing field and keep property compatibility
        self._product_base = product

    def IsTypeBaseChopp(self) -> bool:
        return bool(self.ProductBase.IsChopp())

    def NotTypeBaseChopp(self) -> bool:
        return not self.IsTypeBaseChopp()
    
    def IsTypeBaseWaterIsotonic(self) -> bool:
        return bool(getattr(self.ProductBase, "is_isotonic_water", getattr(self.ProductBase, "IsIsotonicWater", False)))

    def IsTypeBaseReturnable(self) -> bool:
        return bool(getattr(self.ProductBase, "is_returnable", getattr(self.ProductBase, "IsReturnable", False)))

    def IsTypeBaseDisposable(self) -> bool:
        return bool(getattr(self.ProductBase, "is_disposable", getattr(self.ProductBase, "IsDisposable", False)))

    def get_disposable_or_returnable_type(self):
        """
        Tradução do método C#:
        d.IsTypeBaseWaterIsotonic() || !d.IsTypeBaseReturnable()
            ? ContainerType.Disposable 
            : ContainerType.Returnable
        """
        if self.IsTypeBaseWaterIsotonic() or not self.IsTypeBaseReturnable():
            return ContainerType.DISPOSABLE
        return ContainerType.RETURNABLE
        
    # @property
    # def GroupAndSubGroup(self) -> int:
    #     return getattr(self, "_group_and_subgroup", 0)

    @property
    def GroupAndSubGroup(self):
        return int(f"{self.ProductBase.PackingGroup.GroupCode}{self.ProductBase.PackingGroup.SubGroupCode}")
        
    # @GroupAndSubGroup.setter
    # def GroupAndSubGroup(self, value: int):
    #     self._group_and_subgroup = int(value)

    @property
    def Blocked(self) -> bool:
        return bool(self._blocked)

    def Block(self):
        self._blocked = True
    
    # -------------------- Layer / KegExclusive / Bulk properties --------------------
    @property
    def Layer(self) -> bool:
        return bool(self._layer)
    
    @Layer.setter
    def Layer(self, value: bool):
        self._layer = bool(value)
    
    def SetLayer(self, layer: bool):
        self.Layer = layer
    
    @property
    def KegExclusive(self) -> bool:
        return bool(self._keg_exclusive)
    
    @KegExclusive.setter
    def KegExclusive(self, value: bool):
        self._keg_exclusive = bool(value)
    
    def SetKegExclusive(self, keg_exclusive: bool):
        self.KegExclusive = keg_exclusive
    
    @property
    def Bulk(self) -> bool:
        return bool(self._bulk)
    
    @Bulk.setter
    def Bulk(self, value: bool):
        self._bulk = bool(value)
    
    def SetBulk(self, bulk: bool):
        self.Bulk = bulk

    def Clear(self):
        try:
            self._products.clear()
        except Exception:
            self._products = []
        self._assembly_sequence_counter = 0
        self._blocked = False

    def RemoveMountedProduct(self, product: Any):
        try:
            self._products.remove(product)
        except ValueError:
            for p in list(self._products):
                if p is product:
                    self._products.remove(p)
                    break

    @property
    def DifferentPackingGroupQuantity(self) -> int:
        groups = {
            getattr(p, "Product", getattr(p, "product", None)).PackingGroup
            if getattr(getattr(p, "Product", getattr(p, "product", None)), "PackingGroup", None) is not None
            else getattr(getattr(p, "Product", getattr(p, "product", None)), "packing_group", None)
            for p in self._products
        }
        groups = {g for g in groups if g is not None}
        return len(groups)

    @property
    def DifferentProductTypeQuantity(self) -> int:
        types = {
            type(getattr(p, "Product", getattr(p, "product", None))).__name__
            for p in self._products
            if getattr(p, "Product", getattr(p, "product", None)) is not None
        }
        return len(types)

    # @property
    # def DifferentPackingCodeQuantity(self) -> int:
    #     codes = {
    #         getattr(getattr(p, "Product", getattr(p, "product", None)), "Code", getattr(getattr(p, "Product", getattr(p, "product", None)), "code", None))
    #         for p in self._products
    #     }
    #     codes = {c for c in codes if c is not None}
    #     return len(codes)

    @property
    def DifferentPackingCodeQuantity(self) -> int:
        codes = {
            getattr(getattr(p, "Product", getattr(p, "product", None)), "PackingGroup", None)
                and getattr(getattr(getattr(p, "Product", getattr(p, "product", None)), "PackingGroup"), "PackingCode", None)
            for p in self._products
        }
        codes = {c for c in codes if c is not None}
        return len(codes)

    # @property
    # def Remount(self) -> bool:
    #     """Faithful port of C# Pallet.Remount:

    #     True when there's at least one returnable product and at least one
    #     product that is either not returnable or is isotonic water or is chopp.
    #     """
    #     has_returnable = False
    #     has_other = False
    #     for p in self._products:
    #         prod = getattr(p, 'Product', getattr(p, 'product', None))
    #         if prod is None:
    #             continue

    #         is_returnable = bool(getattr(prod, 'is_returnable', getattr(prod, 'IsReturnable', False)))
    #         is_isotonic = bool(getattr(prod, 'is_isotonic_water', getattr(prod, 'IsIsotonicWater', False)))
    #         is_chopp = bool(getattr(prod, 'is_chopp', getattr(prod, 'IsChopp', False)))

    #         if is_returnable:
    #             has_returnable = True

    #         if (not is_returnable) or is_isotonic or is_chopp:
    #             has_other = True

    #         if has_returnable and has_other:
    #             return True

    #     return False

    # snake_case alias
    # @property
    # def remount(self) -> bool:
    #     return self.Remount

    def Clone(self, orders: Optional[List[Any]] = None) -> "Container":
        cloned = deepcopy(self)
        return cloned
    
     # adiciona compatibilidade com API C#
    def GetProducts(self):
        """C# style method returning the mounted products (read-only)."""
        return list(self._products)

    # alias tradicional AddProduct/RemoveProduct
    def AddProduct(self, mounted_product: Any, amount: Optional[int] = None, package: Optional[int] = None):
        return self.AddMountedProduct(mounted_product, amount=amount, package=package)

    def RemoveProduct(self, mounted_product: Any):
        return self.RemoveMountedProduct(mounted_product)

    def HasProducts(self) -> bool:
        return len(self._products) > 0

    # containers helpers (se seu modelo não usa containers, retorna lista vazia)
    def GetContainers(self) -> List[Any]:
        return getattr(self, "_containers", []) or []

    def AddContainer(self, container: Any):
        if not hasattr(self, "_containers"):
            self._containers = []
        self._containers.append(container)

    def RemoveContainer(self, container: Any):
        if hasattr(self, "_containers"):
            try:
                self._containers.remove(container)
            except ValueError:
                pass

    # occupation / weight fields + setters (métodos C#-like)
    @property
    def Occupation(self):
        return getattr(self, "_occupation", 0)

    @Occupation.setter
    def Occupation(self, value):
        self._occupation = value

    def SetOccupation(self, occupation):
        self.Occupation = occupation

    def IncreaseOccupation(self, value):
        self._occupation = getattr(self, "_occupation", 0) + value

    def DecreaseOccupation(self, value):
        self._occupation = getattr(self, "_occupation", 0) - value

    @property
    def Weight(self):
        return getattr(self, "_weight", 0)

    @Weight.setter
    def Weight(self, value):
        self._weight = value

    # manter compatibilidade com nomes PascalCase/pythonic se desejar
    def GetProductBase(self):
        return getattr(self, "_product_base", None)
    # --- pythonic aliases (snake_case) -------------------------------
    @property
    def products(self) -> List[Any]:
        return list(self._products)

    @property
    def product_base(self) -> Optional[Any]:
        return self.ProductBase

    @product_base.setter
    def product_base(self, v: Any):
        self.SetProductBase(v)

    def add_mounted_product(self, mounted_product: Any, amount: Optional[int] = None, package: Optional[int] = None):
        return self.AddMountedProduct(mounted_product, amount=amount, package=package)

    def increase_assembly_sequence(self, mounted_product: Any):
        return self.IncreaseAssemblySequence(mounted_product)

    def set_product_base(self, product: Any):
        return self.SetProductBase(product)

    def is_type_base_chopp(self) -> bool:
        return self.IsTypeBaseChopp()

    def is_type_base_water_isotonic(self) -> bool:
        return self.IsTypeBaseWaterIsotonic()

    def is_type_base_returnable(self) -> bool:
        return self.IsTypeBaseReturnable()

    def is_type_base_disposable(self) -> bool:
        return self.IsTypeBaseDisposable()

    def get_products(self):
        return self.GetProducts()

    def add_product(self, mounted_product: Any, amount: Optional[int] = None, package: Optional[int] = None):
        return self.AddProduct(mounted_product, amount=amount, package=package)

    def remove_product(self, mounted_product: Any):
        return self.RemoveProduct(mounted_product)

    def has_products(self) -> bool:
        return self.HasProducts()

    def get_containers(self) -> List[Any]:
        return self.GetContainers()

    def add_container(self, container: Any):
        return self.AddContainer(container)

    def remove_container(self, container: Any):
        return self.RemoveContainer(container)

    def set_occupation(self, occupation):
        return self.SetOccupation(occupation)

    def increase_occupation(self, value):
        return self.IncreaseOccupation(value)

    def decrease_occupation(self, value):
        return self.DecreaseOccupation(value)

    def get_product_base(self):
        return self.GetProductBase()
    
    @property
    def layer(self) -> bool:
        return self.Layer
    
    @layer.setter
    def layer(self, value: bool):
        self.Layer = value
    
    def set_layer(self, layer: bool):
        return self.SetLayer(layer)
    
    @property
    def keg_exclusive(self) -> bool:
        return self.KegExclusive
    
    @keg_exclusive.setter
    def keg_exclusive(self, value: bool):
        self.KegExclusive = value
    
    def set_keg_exclusive(self, keg_exclusive: bool):
        return self.SetKegExclusive(keg_exclusive)
    
    @property
    def bulk(self) -> bool:
        return self.Bulk
    
    @bulk.setter
    def bulk(self, value: bool):
        self.Bulk = value
    
    def set_bulk(self, bulk: bool):
        return self.SetBulk(bulk)
    
    def HasLayer(self) -> bool:
        if not self.products:
            return False
        return any(i.Product.LayerCode>0 for i in self.products)
    
# ...existin
# g code...