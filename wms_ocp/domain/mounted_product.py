from __future__ import annotations
from decimal import Decimal
from typing import Any, Dict, List, Optional


class MountedProduct:
    """A pragmatic Python port of IMountedProduct interface from C#.

    Stores values in private backing fields (underscore-prefixed). Exposes the
    original PascalCase properties for compatibility and snake_case aliases.
    """

    def __init__(
        self,
        Item: Any = None,
        Product: Any = None,
        Order: Any = None,
        Amount: int = 0,
        Package: int = 0,
        AssemblySequence: int = 0,
        QuantityOfLayers: int = 0,
        FirstLayerIndex: int = 0,
        Splitted: bool = False,
        Customer: int = 0,
        Realocated: bool = False,
        ComplexLoad: bool = False,
        DeliveryOrderQuantity: Optional[Dict[int, int]] = None,
        _PercentOccupationIntoDefaultPalletSize: Decimal = Decimal(0),
        _Occupation: Decimal = Decimal(0),
        _AdditionalOccupation: Decimal = Decimal(0),
        # snake_case overrides
        item: Any = None,
        product: Any = None,
        order: Any = None,
        amount: Optional[int] = None,
        package: Optional[int] = None,
        assembly_sequence: Optional[int] = None,
        quantity_of_layers: Optional[int] = None,
        first_layer_index: Optional[int] = None,
        splitted: Optional[bool] = None,
        customer: Optional[int] = None,
        realocated: Optional[bool] = None,
        complex_load: Optional[bool] = None,
        delivery_order_quantity: Optional[Dict[int, int]] = None,
        percent_occupation_into_default_pallet_size: Optional[Decimal] = None,
        occupation: Optional[Decimal] = None,
        additional_occupation: Optional[Decimal] = None,
    ):
        # prefer snake_case args when provided
        self._item = item if item is not None else Item
        self._product = product if product is not None else Product
        self._order = order if order is not None else Order
        self._amount = int(amount) if amount is not None else int(Amount)
        self._package = int(package) if package is not None else int(Package)
        self._assembly_sequence = int(assembly_sequence) if assembly_sequence is not None else int(AssemblySequence)
        self._quantity_of_layers = int(quantity_of_layers) if quantity_of_layers is not None else int(QuantityOfLayers)
        self._first_layer_index = int(first_layer_index) if first_layer_index is not None else int(FirstLayerIndex)
        self._splitted = bool(splitted) if splitted is not None else bool(Splitted)
        self._customer = int(customer) if customer is not None else int(Customer)
        self._realocated = bool(realocated) if realocated is not None else bool(Realocated)
        self._complex_load = bool(complex_load) if complex_load is not None else bool(ComplexLoad)
        dq = delivery_order_quantity if delivery_order_quantity is not None else DeliveryOrderQuantity
        self._delivery_order_quantity: Dict[int, int] = dict(dq or {})
        self._percent_occupation_into_default_pallet_size = (percent_occupation_into_default_pallet_size if percent_occupation_into_default_pallet_size is not None else _PercentOccupationIntoDefaultPalletSize)
        self._occupation = (occupation if occupation is not None else _Occupation)
        self._additional_occupation = (additional_occupation if additional_occupation is not None else _AdditionalOccupation)

    @staticmethod
    def Build(product: Any, order: Any, quantity_of_layers: int, first_layer_index: int, 
              occupation: Decimal = Decimal(0), customer: int = 0, additional_occupation: Decimal = Decimal(0)) -> "MountedProduct":
        """
        Factory method to build a MountedProduct instance.
        Faithful port of C# MountedProduct.Build() static method.
        
        Args:
            product: IProduct instance
            order: IOrder instance  
            quantity_of_layers: Number of layers
            first_layer_index: Index of first layer
            occupation: Initial occupation (default 0)
            customer: Customer identifier (default 0)
            additional_occupation: Additional occupation (default 0)
        
        Returns:
            New MountedProduct instance
        """
        mounted_product = MountedProduct(
            Product=product,
            Order=order,
            QuantityOfLayers=quantity_of_layers,
            FirstLayerIndex=first_layer_index,
            _Occupation=occupation,
            _AdditionalOccupation=additional_occupation,
            Customer=0,  # Set to 0 initially, then call SetCustomer
        )
        mounted_product.SetCustomer(customer)
        return mounted_product


    # Basic setters that mirror C# interface
    def SetProduct(self, product: Any):
        self.Product = product

    def SetLayers(self, layers: int):
        self.QuantityOfLayers = layers

    def AddAmount(self, amount: int):
        self.Amount += amount

    def AddPackage(self, package: int):
        self.Package += package

    def SetFirstLayerIndex(self, index: int):
        self.FirstLayerIndex = index

    def SetAssemblySequence(self, assemblySequence: int):
        self.AssemblySequence = assemblySequence

    def HasLayerConfigurationWithQuantityToLayer(self) -> bool:
        return self.QuantityOfLayers > 0

    def SubtractAmount(self, amount: int):
        self.Amount = max(0, self.Amount - amount)

    def Split(self):
        self.Splitted = True

    def Clone(self, orders: List[Any]) -> "MountedProduct":
        # Shallow clone: keep product and item references, copy scalars and dict
        clone = MountedProduct(
            Item=self.Item,
            Product=self.Product,
            Order=self.Order,
            Amount=self.Amount,
            Package=self.Package,
            AssemblySequence=self.AssemblySequence,
            QuantityOfLayers=self.QuantityOfLayers,
            FirstLayerIndex=self.FirstLayerIndex,
            Splitted=self.Splitted,
            Customer=self.Customer,
            Realocated=self.Realocated,
            ComplexLoad=self.ComplexLoad,
            DeliveryOrderQuantity=dict(self.DeliveryOrderQuantity),
            _PercentOccupationIntoDefaultPalletSize=self._PercentOccupationIntoDefaultPalletSize,
            _Occupation=self._Occupation,
            _AdditionalOccupation=self._AdditionalOccupation,
        )
        # Orders arg is accepted for interface parity; not used in this simple clone
        return clone

    # @property
    # def PercentOccupationIntoDefaultPalletSize(self) -> Decimal:
    #     # If an explicit stored value exists and is non-zero, prefer it
    #     try:
    #         val = self._percent_occupation_into_default_pallet_size
    #         if val is not None:
    #             try:
    #                 if float(val) != 0:
    #                     return Decimal(val)
    #             except Exception:
    #                 # non-numeric stored value — ignore and compute dynamically
    #                 pass
    #     except Exception:
    #         pass

    #     # Compute as: (Amount / Product.PalletSetting.Quantity) * 100 (C# parity)
    #     try:
    #         prod = getattr(self, 'Product', None)
    #         if prod is None:
    #             return Decimal(0)

    #         pallet_setting = getattr(prod, 'PalletSetting', getattr(prod, 'pallet_setting', None))
    #         if pallet_setting is None:
    #             return Decimal(0)

    #         qty = getattr(pallet_setting, 'Quantity', getattr(pallet_setting, 'quantity', None))
    #         if qty in (None, 0):
    #             return Decimal(0)

    #         amount = Decimal(int(self.Amount))
    #         qty_dec = Decimal(int(qty))
    #         return (amount / qty_dec) * Decimal(100)
    #     except Exception:
    #         return Decimal(0)

    @property
    def PercentOccupationIntoDefaultPalletSize(self) -> Decimal:
        qty = Decimal(self.Product.PalletSetting.Quantity)
        if qty == 0:
            return Decimal(0)
        return (Decimal(self.Amount) / qty) * Decimal(100)

        
    @property
    def Occupation(self) -> Decimal:
        return self._Occupation

    @property
    def AdditionalOccupation(self) -> Decimal:
        return self._AdditionalOccupation

    def SetOccupation(self, occupation: Decimal):
        self._Occupation = occupation

    def SetCustomer(self, customer: int):
        # C# MountedProduct.SetCustomer sets ComplexLoad when customer != default (0)
        try:
            self.Customer = int(customer) if customer is not None else 0
        except Exception:
            self.Customer = customer
        try:
            self.ComplexLoad = (int(self.Customer) != 0)
        except Exception:
            self.ComplexLoad = bool(self.Customer)

    def AddDeliveryOrderQuantity(self, deliveryOrder: int, quantity: int):
        self.DeliveryOrderQuantity[deliveryOrder] = self.DeliveryOrderQuantity.get(deliveryOrder, 0) + quantity

    def GetSideQuantity(self, side: Any) -> int:
        # Side semantics depend on TruckSafeSide; here we provide a reasonable default: sum of quantities
        return sum(self.DeliveryOrderQuantity.values())

    def SetAdditionalOccupation(self, additionalOccupation: Decimal):
        self._AdditionalOccupation = additionalOccupation
    
    # PascalCase properties mapping to private fields
    @property
    def Item(self) -> Any:
        return self._item

    @Item.setter
    def Item(self, v: Any):
        self._item = v

    @property
    def Product(self) -> Any:
        return self._product

    @Product.setter
    def Product(self, v: Any):
        self._product = v

    @property
    def Order(self) -> Any:
        return self._order

    @Order.setter
    def Order(self, v: Any):
        self._order = v

    @property
    def Amount(self) -> int:
        return int(self._amount)

    @Amount.setter
    def Amount(self, v: int):
        self._amount = int(v)

    @property
    def Package(self) -> int:
        return int(self._package)

    @Package.setter
    def Package(self, v: int):
        self._package = int(v)

    @property
    def AssemblySequence(self) -> int:
        return int(self._assembly_sequence)

    @AssemblySequence.setter
    def AssemblySequence(self, v: int):
        self._assembly_sequence = int(v)

    @property
    def QuantityOfLayers(self) -> int:
        return int(self._quantity_of_layers)

    @QuantityOfLayers.setter
    def QuantityOfLayers(self, v: int):
        self._quantity_of_layers = int(v)

    @property
    def FirstLayerIndex(self) -> int:
        return int(self._first_layer_index)

    @FirstLayerIndex.setter
    def FirstLayerIndex(self, v: int):
        self._first_layer_index = int(v)

    @property
    def Splitted(self) -> bool:
        return bool(self._splitted)

    @Splitted.setter
    def Splitted(self, v: bool):
        self._splitted = bool(v)

    @property
    def Customer(self) -> int:
        return int(self._customer)

    @Customer.setter
    def Customer(self, v: int):
        try:
            self._customer = int(v)
        except Exception:
            self._customer = v
        try:
            # keep ComplexLoad in sync like C# SetCustomer
            self._complex_load = (int(self._customer) != 0)
        except Exception:
            self._complex_load = bool(self._customer)

    @property
    def Realocated(self) -> bool:
        return bool(self._realocated)

    @Realocated.setter
    def Realocated(self, v: bool):
        self._realocated = bool(v)

    @property
    def ComplexLoad(self) -> bool:
        return bool(self._complex_load)

    @ComplexLoad.setter
    def ComplexLoad(self, v: bool):
        self._complex_load = bool(v)

    @property
    def DeliveryOrderQuantity(self) -> Dict[int,int]:
        return dict(self._delivery_order_quantity)

    @DeliveryOrderQuantity.setter
    def DeliveryOrderQuantity(self, v: Dict[int,int]):
        self._delivery_order_quantity = dict(v or {})

    @property
    def _PercentOccupationIntoDefaultPalletSize(self) -> Decimal:
        return self._percent_occupation_into_default_pallet_size

    @property
    def percent_occupation_into_default_pallet_size(self) -> Decimal:
        return self.PercentOccupationIntoDefaultPalletSize

    @property
    def _Occupation(self) -> Decimal:
        return self._occupation

    @_Occupation.setter
    def _Occupation(self, v: Decimal):
        try:
            self._occupation = Decimal(v)
        except Exception:
            self._occupation = v

    @property
    def _AdditionalOccupation(self) -> Decimal:
        return self._additional_occupation
    
    @_AdditionalOccupation.setter
    def _AdditionalOccupation(self, v: Decimal):
        try:
            self._additional_occupation = Decimal(v)
        except Exception:
            self._additional_occupation = v

    # --- pythonic aliases for attributes (snake_case) -----------------
    @property
    def item(self) -> Any:
        return self.Item

    @item.setter
    def item(self, v: Any):
        self.Item = v

    @property
    def product(self) -> Any:
        return self.Product

    @product.setter
    def product(self, v: Any):
        self.Product = v

    @property
    def order(self) -> Any:
        return self.Order

    @order.setter
    def order(self, v: Any):
        self.Order = v

    @property
    def amount(self) -> int:
        return self.Amount

    @amount.setter
    def amount(self, v: int):
        self.Amount = v

    @property
    def package(self) -> int:
        return self.Package

    @package.setter
    def package(self, v: int):
        self.Package = v

    @property
    def occupation(self) -> Decimal:
        return self._Occupation

    @occupation.setter
    def occupation(self, v: Decimal):
        self._Occupation = v

    @property
    def additional_occupation(self) -> Decimal:
        return self._AdditionalOccupation

    @additional_occupation.setter
    def additional_occupation(self, v: Decimal):
        self._AdditionalOccupation = v

    # --- pythonic method aliases ------------------------------------
    def set_product(self, product: Any):
        return self.SetProduct(product)

    def set_layers(self, layers: int):
        return self.SetLayers(layers)

    def set_assembly_sequence(self, assembly_sequence: int):
        return self.SetAssemblySequence(assembly_sequence)

    def add_amount(self, amount: int):
        return self.AddAmount(amount)

    def add_package(self, package: int):
        return self.AddPackage(package)

    def subtract_amount(self, amount: int):
        return self.SubtractAmount(amount)

    def set_occupation(self, occupation: Decimal):
        return self.SetOccupation(occupation)

    def set_additional_occupation(self, additional: Decimal):
        return self.SetAdditionalOccupation(additional)

    def clone(self, orders: List[Any]) -> "MountedProduct":
        return self.Clone(orders)

    # additional snake_case aliases
    def set_customer(self, customer: int):
        return self.SetCustomer(customer)
    
    def SetRealocated(self, realocated: bool):
        self.Realocated = realocated
    
    def set_realocated(self, realocated: bool):
        return self.SetRealocated(realocated)

    def add_delivery_order_quantity(self, delivery_order: int, quantity: int):
        return self.AddDeliveryOrderQuantity(delivery_order, quantity)

    def get_side_quantity(self, side: Any) -> int:
        return self.GetSideQuantity(side)

    # --- Product type checking methods (used by MountedProductList filters) ---
    def IsChopp(self) -> bool:
        """Check if product is chopp/draft beer."""
        try:
            if self.Product is None:
                return False
            return self.Product.is_chopp()
        except Exception:
            return False

    def IsReturnable(self) -> bool:
        """Check if product is returnable."""
        try:
            if self.Product is None:
                return False
            return self.Product.is_returnable()
        except Exception:
            return False

    def IsDisposable(self) -> bool:
        """Check if product is disposable (not returnable)."""
        return not self.IsReturnable()

    def IsIsotonicWater(self) -> bool:
        """Check if product is isotonic water."""
        try:
            if self.Product is None:
                return False
            return self.Product.is_isotonic_water()
        except Exception:
            return False

    def IsMarketplace(self) -> bool:
        """Check if product is marketplace."""
        try:
            if self.Product is None:
                return False
            return self.Product.is_marketplace()
        except Exception:
            return False
    
    def NotMarketplace(self) -> bool:
        """Check if product is marketplace."""
        try:
            if self.Product is None:
                return False
            return self.Product.not_marketplace()
        except Exception:
            return False
        
    def IsTopOfPallet(self) -> bool:
        """Check if product is top of pallet."""
        try:
            if self.Product is None:
                return False
            return self.Product.is_top_of_pallet()
        except Exception:
            return False

    def IsBasePallet(self) -> bool:
        """Check if product is base pallet."""
        try:
            if self.Product is None:
                return False
            return self.Product.is_base_pallet()
        except Exception:
            return False

    # snake_case aliases
    def is_chopp(self) -> bool:
        return self.IsChopp()

    def is_returnable(self) -> bool:
        return self.IsReturnable()

    def is_disposable(self) -> bool:
        return self.IsDisposable()

    def is_isotonic_water(self) -> bool:
        return self.IsIsotonicWater()

    def is_top_of_pallet(self) -> bool:
        return self.IsTopOfPallet()

    def is_base_pallet(self) -> bool:
        return self.IsBasePallet()

    # convenience: match C# naming used in rules
    def is_disposable_product(self) -> bool:
        """Alias used in rules: whether product is disposable (not returnable)."""
        try:
            return self.is_disposable()
        except Exception:
            return False

    def is_disposable_not_top_pallet(self) -> bool:
        """Returns True if product is disposable and NOT marked as TopOfPallet.

        Mirrors intent used by C# SeparateRemountBaysAndLayerBaysRule filtering.
        """
        try:
            return self.is_disposable() and (not self.is_top_of_pallet())
        except Exception:
            return False