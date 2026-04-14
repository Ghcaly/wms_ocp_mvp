from __future__ import annotations
# ...existing code...
from typing import List, Optional, Any
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from copy import deepcopy

class MountedSpace:

    def __init__(
        self,
        space: Any = None,
        order: Any = None,
        containers: Optional[List[Any]] = None,
        products: Optional[List[Any]] = None,
        occupation: Decimal = Decimal(0),
        weight: Decimal = Decimal(0),
        blocked: bool = False,
        id: Optional[int] = None,
    ):
        # private backing fields
        self._id = id
        self._space = space
        self._order = order
        # containers represent pallets/containers inside the mounted space
        self._containers: List[Any] = containers or []
        # legacy flat products list (kept for compatibility)
        self._products: List[Any] = products or []
        # numeric fields
        self._occupation = Decimal(occupation)
        self._weight = Decimal(weight)
        self._blocked = bool(blocked)

    # Properties mapping to private fields (PascalCase compatibility)
    @property
    def Id(self) -> Optional[int]:
        return self._id

    @Id.setter
    def Id(self, v: Optional[int]):
        self._id = v

    @property
    def Space(self) -> Any:
        return self._space

    @Space.setter
    def Space(self, v: Any):
        self._space = v

    @property
    def space(self) -> Any:
        """snake_case alias for Space"""
        return self._space

    @space.setter
    def space(self, v: Any):
        self._space = v

    @property
    def Order(self) -> Any:
        return self._order

    @Order.setter
    def Order(self, v: Any):
        self._order = v

    @property
    def Containers(self) -> List[Any]:
        return self._containers

    @property
    def containers(self) -> List[Any]:
        return self._containers
    
    @Containers.setter
    def Containers(self, v: List[Any]):
        self._containers = v or []

    @property
    def Products(self) -> List[Any]:
        return self._products

    @Products.setter
    def Products(self, v: List[Any]):
        self._products = v or []

    @property
    def Occupation(self) -> Decimal:
        return Decimal(self._occupation)

    @Occupation.setter
    def Occupation(self, v: Decimal):
        self._occupation = self._truncate_two_decimals(Decimal(v))

    # @property
    # def Weight(self) -> Decimal:
    #     return Decimal(self._weight)

    # @Weight.setter
    # def Weight(self, v: Decimal):
    #     self._weight = Decimal(v)

    @property
    def Blocked(self) -> bool:
        return bool(self._blocked)

    @Blocked.setter
    def Blocked(self, value: bool):
        self._blocked = bool(value)

    # -------------------- Product access --------------------
    # def GetProducts(self) -> List[Any]:
    #     """Return flattened list of mounted products (from containers if present, else legacy Products)."""
    #     prods: List[Any] = []
    #     if self.Containers:
    #         for c in self.Containers:
    #             try:
    #                 prods.extend(c.get_products())
    #             except Exception:
    #                 # fallback: try attribute
    #                 prods.extend(getattr(c, "Products", []) or [])
    #         return prods
    #     return self.Products
    def GetProducts(self) -> List[Any]:
        """
        100% faithful to C#:
        mountedSpace.Containers.SelectMany(x => x.Products)
        """
        if not self.Containers:
            return []

        products: List[Any] = []
        for c in self.Containers:
            products.extend(getattr(c, "Products", []) or [])

        return products


    # -------------------- Container management --------------------
    def AddContainer(self, container: Any):
        """Add a container/pallet to this mounted space."""
        self.Containers.append(container)

    def GetContainers(self) -> List[Any]:
        """Get list of containers (mirrors C# GetContainers)."""
        return self.Containers

    def get_containers(self) -> List[Any]:
        """snake_case alias for GetContainers."""
        return self.GetContainers()

    # -------------------- Occupation / weight management --------------------
    @property
    def occupation(self) -> Decimal:
        return Decimal(self.Occupation)

    @occupation.setter
    def occupation(self, value: Decimal):
        self.Occupation = self._truncate_two_decimals(Decimal(value))

    @property
    def OccupationRemaining(self) -> Decimal:
        try:
            size = Decimal(getattr(self.Space, "Size", getattr(self.Space, "size", 0)))
            return self._truncate_two_decimals(Decimal(size) - Decimal(self.Occupation))
        except Exception:
            return Decimal(0)

    @property
    def OccupiedPercentage(self) -> float:
        try:
            size = Decimal(getattr(self.Space, "Size", getattr(self.Space, "size", 0)))
            if size == 0:
                return 0.0
            return float((Decimal(self.Occupation) / size) * Decimal(100))
        except Exception:
            return 0.0

    # @property
    # def Full(self) -> bool:
    #     try:
    #         size = Decimal(getattr(self.Space, "Size", getattr(self.Space, "size", 0)))
    #         return Decimal(self.Occupation) >= size
    #     except Exception:
    #         return False

    @property
    def Full(self):
        pallets_bulk = all(c.Bulk for c in self.Containers)
        space_size = self.Space.Size if self.Space else 0
        return pallets_bulk or self.Occupation >= space_size

    # @property
    # def Full(self) -> bool:
    #     try:
    #         # C# logic: if all pallet containers are Bulk => Full, otherwise occupation >= space size
    #         pallets = [c for c in (self.Containers or []) if (hasattr(c, 'Bulk') or hasattr(c, 'SetBulk') or hasattr(c, 'set_bulk'))]
    #         if pallets:
    #             try:
    #                 all_bulk = all(bool(getattr(p, 'Bulk', getattr(p, 'bulk', False))) for p in pallets)
    #                 if all_bulk:
    #                     return True
    #                 else:
    #                     return False
    #             except Exception:
    #                 # if bulk-check fails, fallthrough to size-based check
    #                 pass

    #         size = Decimal(getattr(self.Space, "Size", getattr(self.Space, "size", 0)))
    #         return Decimal(self.Occupation) >= size
    #     except Exception:
    #         return False
        
    @property
    def Blocked(self) -> bool:
        return bool(self.__dict__.get("_blocked", False))

    @Blocked.setter
    def Blocked(self, value: bool):
        self.__dict__["_blocked"] = bool(value)

    def SetOccupation(self, occupation: Decimal):
        """Set occupation (mirrors C# SetOccupation)."""
        self.Occupation = self._truncate_two_decimals(Decimal(occupation))

    def IncreaseOccupation(self, occupation: Decimal):
        """Increase occupation by value (mirrors C# IncreaseOccupation)."""
        new_val = Decimal(self.Occupation) + Decimal(occupation)
        self.Occupation = self._truncate_two_decimals(new_val)

    def DecreaseOccupation(self, occupation: Decimal):
        """Decrease occupation by value (mirrors C# DecreaseOccupation)."""
        new_val = Decimal(self.Occupation) - Decimal(occupation)
        self.Occupation = self._truncate_two_decimals(new_val)

    # -------------------- Block / clear --------------------
    def Block(self):
        self.Blocked = True

    def UnBlock(self):
        self.Blocked = False

    def Clear(self):
        """
        Clear mounted space (clear products from containers but keep containers).
        C# behavior: foreach (var container in _containers) container.Clear();
        This preserves containers with their ProductBase intact.
        """
        # Clear each container (removes products but keeps container and ProductBase)
        for container in self.Containers:
            try:
                container.Clear()
            except Exception:
                pass
        
        # Clear legacy products list
        try:
            self.Products.clear()
        except Exception:
            pass
        
        # Reset occupation and weight
        self.Occupation = Decimal(0)
        self.Weight = Decimal(0)

    # -------------------- Clone / setters --------------------
    def Clone(self, orders: Optional[List[Any]] = None, spaces: Optional[List[Any]] = None) -> "MountedSpace":
        """
        Create a shallow/deep copy suitable for snapshot operations.
        Mirrors C# Clone(IList<IOrder>, IList<ISpace>) semantics used by rules.
        """
        clone = MountedSpace(
            space=deepcopy(self.Space),
            order=deepcopy(self.Order),
            containers=deepcopy(self.Containers),
            products=deepcopy(self.Products),
            occupation=Decimal(self.Occupation),
            weight=Decimal(self.Weight),
            blocked=bool(self.Blocked),
            id=self.Id,
        )
        return clone

    def SetSpace(self, space: Any):
        self.Space = space

    def SetOrder(self, order: Any):
        self.Order = order

    # -------------------- Utilities --------------------
    def _truncate_two_decimals(self, value: Decimal) -> Decimal:
        """Truncate Decimal to two decimals (towards zero) like C# Math.Truncate(100 * value) / 100."""
        v = Decimal(value)
        multiplied = v * Decimal(100)
        if multiplied >= 0:
            integral = multiplied.to_integral_value(rounding=ROUND_DOWN)
        else:
            integral = multiplied.to_integral_value(rounding=ROUND_UP)
        return integral / Decimal(100)

    # -------------------- Pythonic aliases (optional) --------------------
    @property
    def weight(self) -> Decimal:
        return Decimal(self.Weight)

    # @weight.setter
    # def weight(self, value: Decimal):
    #     self.Weight = Decimal(value)

    @property
    def Weight(self) -> Decimal:
        """
        Compute mounted-space weight from contained products/pallets.
        Mirrors C# behavior: sum product total weights instead of keeping a separate mutable field.
        """
        try:
            total = Decimal(0)
            products = self.GetProducts() or []
            for mp in products:
                total += Decimal(float(mp.Product.GrossWeight) * float(mp.Amount))
            return self._truncate_two_decimals(total)
        except Exception:
            return Decimal(self._weight)

    @Weight.setter
    def Weight(self, v: Decimal):
        # keep setter for compatibility (will be ignored by getter which computes current sum)
        try:
            self._weight = Decimal(v)
        except Exception:
            self._weight = Decimal(0)

    @property
    def occupation_remaining(self) -> Decimal:
        return self.OccupationRemaining

    @property
    def occupied_percentage(self) -> float:
        return self.OccupiedPercentage

    @property
    def full(self) -> bool:
        return self.Full

    # --- snake_case aliases for methods --------------------------------
    def get_products(self) -> List[Any]:
        return self.GetProducts()

    def GetItems(self) -> List[Any]:
        """
        Get unique items from all containers in this mounted space.
        Mirrors C# GetItems: returns distinct items (not mounted products) that are palletizable.
        C#: mountedSpace.Containers.SelectMany(x => x.Products.Where(x => x.Product.CanBePalletized))
                                    .Select(x => x.Order.Items.First(y => y.Product == x.Product))
        """
        items = []
        seen_products = set()
        
        for container in self.Containers:
            products = getattr(container, 'Products', [])
            for mp in products:
                product = getattr(mp, 'Product', None)
                if not product:
                    continue
                
                # Check if product can be palletized
                can_be_palletized = getattr(product, 'CanBePalletized', True)
                if not can_be_palletized:
                    continue
                
                # Use product code as unique identifier
                product_code = getattr(product, 'Code', id(product))
                if product_code in seen_products:
                    continue
                
                seen_products.add(product_code)
                
                # Get original item from order
                order = getattr(mp, 'Order', self.Order)
                if order:
                    order_items = getattr(order, 'Items', [])
                    # Find item with matching product
                    matching_item = next(
                        (item for item in order_items if getattr(item, 'Product', None) == product),
                        None
                    )
                    if matching_item:
                        items.append(matching_item)
        
        return items

    def get_items(self) -> List[Any]:
        return self.GetItems()

    def add_container(self, container: Any):
        return self.AddContainer(container)

    def set_occupation(self, occupation: Decimal):
        return self.SetOccupation(occupation)

    def increase_occupation(self, occupation: Decimal):
        return self.IncreaseOccupation(occupation)

    def decrease_occupation(self, occupation: Decimal):
        return self.DecreaseOccupation(occupation)

    def block(self):
        return self.Block()

    def unblock(self):
        return self.UnBlock()

    def clear(self):
        return self.Clear()

    def clone(self, orders: Optional[List[Any]] = None, spaces: Optional[List[Any]] = None) -> "MountedSpace":
        return self.Clone(orders=orders, spaces=spaces)

    def set_space(self, space: Any):
        return self.SetSpace(space)

    def set_order(self, order: Any):
        return self.SetOrder(order)

    # -------------------- Type checking methods (from MountedSpaceExtensions.cs) --------------------
    def IsChopp(self) -> bool:
        """Check if all containers in mounted space are Chopp type"""
        if not self.Containers:
            return False
        return all(getattr(c, 'IsTypeBaseChopp', lambda: False)() for c in self.Containers)

    def is_chopp(self) -> bool:
        return self.IsChopp()

    def NotChopp(self) -> bool:
        """Check if all containers are NOT Chopp type"""
        if not self.Containers:
            return True
        return all(not c.IsTypeBaseChopp() for c in self.Containers)

    def not_chopp(self) -> bool:
        return self.NotChopp()

    def IsReturnable(self) -> bool:
        """Check if all containers in mounted space are Returnable type"""
        if not self.Containers:
            return False
        return all(getattr(c, 'IsTypeBaseReturnable', lambda: False)() for c in self.Containers)

    def is_returnable(self) -> bool:
        return self.IsReturnable()

    def NotReturnable(self) -> bool:
        """Check if all containers are NOT Returnable type"""
        if not self.Containers:
            return True
        return all(not getattr(c, 'IsTypeBaseReturnable', lambda: False)() for c in self.Containers)

    def not_returnable(self) -> bool:
        return self.NotReturnable()

    def IsDisposable(self) -> bool:
        """Check if containers are Disposable type"""
        if not self.Containers:
            return False
        return all(getattr(c, 'IsTypeBaseDisposable', lambda: False)() for c in self.Containers)

    def is_disposable(self) -> bool:
        return self.IsDisposable()

    def NotIsotonicWater(self) -> bool:
        """Check if all containers are NOT IsotonicWater type"""
        if not self.Containers:
            return True
        return all(not getattr(c, 'IsTypeBaseWaterIsotonic', lambda: False)() for c in self.Containers)

    def not_isotonic_water(self) -> bool:
        return self.NotIsotonicWater()

    # -------------------- Space status checking methods --------------------
    def HasSpaceAndNotBlocked(self) -> bool:
        """Check if space is not full and not blocked"""
        return not self.Full and not self.Blocked

    def has_space_and_not_blocked(self) -> bool:
        return self.HasSpaceAndNotBlocked()
    
    def HasSpace(self) -> bool:
        """Check if space is not full"""
        return not self.Full
    
    def has_space(self) -> bool:
        return self.HasSpace()

    def IsOccupied(self) -> bool:
        """Check if occupation > 0"""
        return self.Occupation > 0

    def is_occupied(self) -> bool:
        return self.IsOccupied()

    def IsEmpty(self) -> bool:
        """Check if occupation == 0"""
        return self.Occupation == 0

    def is_empty(self) -> bool:
        return self.IsEmpty()
    
    def IsBlocked(self) -> bool:
        """Check if space is blocked"""
        return self.Blocked
    
    def is_blocked(self) -> bool:
        return self.IsBlocked()

    # -------------------- Layer and feature checking methods --------------------
    # def HasLayer(self) -> bool:
    #     """Check if any pallet container has Layer flag"""
    #     if not self.Containers:
    #         return False
    #     return any(getattr(c, 'Layer', False) for c in self.Containers)

    def has_layer(self) -> bool:
        return self.HasLayer()

    def NotLayer(self) -> bool:
        """Check if all pallets do NOT have Layer flag"""
        if not self.Containers:
            return True
        return all(not getattr(c, 'Layer', False) for c in self.Containers)

    def not_layer(self) -> bool:
        return self.NotLayer()

    def NotKegExclusive(self) -> bool:
        """Check if all pallets are NOT keg exclusive"""
        if not self.Containers:
            return True
        return all(not getattr(c, 'KegExclusive', False) for c in self.Containers)

    def not_keg_exclusive(self) -> bool:
        return self.NotKegExclusive()

    def GetNextLayer(self) -> int:
        """Get next layer index (max FirstLayerIndex + 1)"""
        max_layer = 0
        for container in self.Containers:
            products = getattr(container, 'Products', [])
            for prod in products:
                first_layer = getattr(prod, 'FirstLayerIndex', 0)
                if first_layer > max_layer:
                    max_layer = first_layer
        return max_layer + 1

    def get_next_layer(self) -> int:
        return self.GetNextLayer()

    def IsNewGroup(self, item: Any) -> bool:
        """Check if item's packing group is new to this mounted space"""
        if not self.Containers:
            return True
        
        # Get all existing group codes
        existing_groups = set()
        for container in self.Containers:
            products = getattr(container, 'Products', [])
            for prod in products:
                product = getattr(prod, 'Product', None)
                if product:
                    packing_group = getattr(product, 'PackingGroup', None)
                    if packing_group:
                        group_code = getattr(packing_group, 'GroupCode', None)
                        if group_code is not None:
                            existing_groups.add(group_code)
        
        # Check if item's group code is in existing groups
        item_product = getattr(item, 'Product', None)
        if not item_product:
            return True
        
        item_packing_group = getattr(item_product, 'PackingGroup', None)
        if not item_packing_group:
            return True
        
        item_group_code = getattr(item_packing_group, 'GroupCode', None)
        return item_group_code not in existing_groups

    def is_new_group(self, item: Any) -> bool:
        return self.IsNewGroup(item)
    
    def GetFirstPallet(self) -> Optional[Any]:
        """Get first container/pallet in the mounted space"""
        if self.Containers and len(self.Containers) > 0:
            return self.Containers[0]
        return None
    
    def get_first_pallet(self) -> Optional[Any]:
        return self.GetFirstPallet()

    def IsRemount(self) -> bool:
        """Check if all pallets/containers in mounted space are remount (C#: Containers.OfType<IPallet>().All(y => y.Remount))"""
        if not self.Containers:
            return False
        # Filter only Pallet type containers (skip non-pallet containers if any)
        pallets = [c for c in self.Containers if c.Remount]
        if not pallets:
            return False
        return all(p.Remount for p in pallets)

    def is_remount(self) -> bool:
        return self.IsRemount()

    def IsSplitted(self) -> bool:
        """Check if any product in any pallet is splitted (C#: Containers.OfType<IPallet>().Any(y => y.Products.Any(z => z.Splitted)))"""
        if not self.Containers:
            return False
        
        for container in self.Containers:
            products = getattr(container, 'Products', [])
            for prod in products:
                if getattr(prod, 'Splitted', False):
                    return True
        return False

    def is_splitted(self) -> bool:
        return self.IsSplitted()

    def HasLayer(self) -> bool:
        if not self.Containers:
            return False
        return any(c.HasLayer() for c in self.Containers)

    def has_layer(self) -> bool:
        return self.HasLayer()

    def NotKegExclusive(self) -> bool:
        """Check if all pallets are NOT keg exclusive (C#: Containers.OfType<IPallet>().All(y => !y.KegExclusive))"""
        if not self.Containers:
            return True
        pallets = [c for c in self.Containers if hasattr(c, 'KegExclusive')]
        if not pallets:
            return True
        return all(not getattr(p, 'KegExclusive', False) for p in pallets)

    def not_keg_exclusive(self) -> bool:
        return self.NotKegExclusive()