

from collections.abc import Callable
from typing import Any
from ..domain.ordered_space_list import OrderedSpaceList


class SpaceList:
    """Wrapper for lists of Space objects providing C#-like LINQ helpers used by rules."""

    def __init__(self, spaces):
        self.spaces = list(spaces) if spaces is not None else []

    def concat(self, other):
        return SpaceList(self.spaces + list(other))

    def Concat(self, other):
        return self.concat(other)

    def NotBalanced(self):
        """
        Return spaces that are not marked as Balanced (and not blocked).
        Mirrors C# semantics: exclude spaces with Balanced == true and Blocked == true.
        """
        return SpaceList([s for s in self if not getattr(s, "Balanced", False) and not getattr(s, "Blocked", False)])

    def Balanced(self):
        """Return spaces that are marked as Balanced (and not blocked)."""
        return SpaceList([s for s in self if getattr(s, "Balanced", False) and not getattr(s, "Blocked", False)])


    def distinct(self):
        seen = set()
        result = []
        for s in self.spaces:
            size = getattr(s, 'Size', getattr(s, 'size', None))
            number = getattr(s, 'Number', getattr(s, 'number', None))
            side = getattr(s, 'Side', getattr(s, 'side', None))
            key = (size, number, side)
            if key in seen:
                continue
            seen.add(key)
            result.append(s)
        return SpaceList(result)

    def Distinct(self):
        return self.distinct()

    # def ordered_by_size_and_number(self):
    #     sorted_spaces = sorted(self.spaces, key=lambda s: (getattr(s, 'Size', getattr(s, 'size', None)) or 0, getattr(s, 'Number', getattr(s, 'number', None)) or 0))
    #     return SpaceList(sorted_spaces)
    
    def ordered_by_size_and_number(self):
        # C# mirrors: OrderByDescending(p => (int)p.Size).ThenBy(p => p.Number)
        # Stable sort preserves original order for equal keys (A before M within same bay number)
        sorted_spaces = sorted(
            self.spaces,
            key=lambda s: (
                -(getattr(s, 'Size', getattr(s, 'size', 0)) or 0),  # Size DESC
                getattr(s, 'Number', getattr(s, 'number', 0)),       # Number ASC
            )
        )
        return SpaceList(sorted_spaces)

    def OrderedBySizeAndNumber(self):
        return self.ordered_by_size_and_number()

    def ordered_by_package_then_occupation(self, context):
        """Order spaces: package-containing spaces first, then by occupation ascending.

        Mirrors C# OrderedByPackageThenOccupation(spaces, context).
        """
        def key_fn(s):
            try:
                ms = context.GetMountedSpace(s) if hasattr(context, 'GetMountedSpace') else context.get_mounted_space(s)
                products = ms.GetProducts() if ms is not None and hasattr(ms, 'GetProducts') else (ms.get_products() if ms is not None and hasattr(ms, 'get_products') else [])
                # detect package presence on any mounted product
                is_package = False
                for p in products:
                    prod = getattr(p, 'Product', getattr(p, 'product', None))
                    if prod is None:
                        continue
                    if getattr(prod, 'IsPackage', False) or getattr(prod, 'is_package', False):
                        is_package = True
                        break
                occupation = getattr(ms, 'Occupation', getattr(ms, 'occupation', 0)) if ms is not None else 0
                return (-int(bool(is_package)), occupation)
            except Exception as e: print(f"Error:: {e}"); return (0, 0)

        sorted_spaces = sorted(self.spaces, key=key_fn)
        return SpaceList(sorted_spaces)

    def FirstOrDefault(self, predicate=None):
        """
        Return the first element that matches predicate or the first element if no predicate supplied.
        Returns None if no element found (mirrors LINQ FirstOrDefault).
        """
        if predicate is None:
            return self[0] if len(self) > 0 else None
        for x in self:
            if predicate(x):
                return x
        return None
    
    def matching(self, cond):
        """Aplica uma função de filtro genérica"""
        if cond:
            filtrados = [ms for ms in self.spaces if cond(ms)]
            return SpaceList(filtrados)
        return self
    
    def OrderedByPackageThenOccupation(self, context):
        return self.ordered_by_package_then_occupation(context)

    def ordered_by_package_then_box_template_then_occupation(self, context):
        """Order spaces: package-containing desc, box-template-containing desc, then occupation asc.

        Mirrors C# OrderedByPackageThenBoxTemplateThenOccupation.
        """
        def key_fn(s):
            try:
                ms = context.GetMountedSpace(s) if hasattr(context, 'GetMountedSpace') else context.get_mounted_space(s)
                products = ms.GetProducts() if ms is not None and hasattr(ms, 'GetProducts') else (ms.get_products() if ms is not None and hasattr(ms, 'get_products') else [])
                is_package = False
                is_box = False
                for p in products:
                    prod = getattr(p, 'Product', getattr(p, 'product', None))
                    if prod is None:
                        continue
                    if getattr(prod, 'IsPackage', False) or getattr(prod, 'is_package', False):
                        is_package = True
                    if getattr(prod, 'IsBoxTemplate', False) or getattr(prod, 'is_box_template', False):
                        is_box = True
                occupation = getattr(ms, 'Occupation', getattr(ms, 'occupation', 0)) if ms is not None else 0
                return (-int(bool(is_package)), -int(bool(is_box)), occupation)
            except Exception as e: print(f"Error:: {e}"); return (0, 0, 0)

        sorted_spaces = sorted(self.spaces, key=key_fn)
        return SpaceList(sorted_spaces)

    def driver_side(self):
        """Filtra mounted spaces no lado do motorista (Driver Side)"""
        filtrados = [s for s in self.spaces if s.IsDriverSide()]
        return SpaceList(filtrados)

    def helper_side(self):
        """Filtra mounted spaces no lado do ajudante (Helper Side)"""
        filtrados = [s for s in self.spaces if s.IsHelperSide()]
        return SpaceList(filtrados)
    
    def OrderedByPackageThenBoxTemplateThenOccupation(self, context):
        return self.ordered_by_package_then_box_template_then_occupation(context)

    def OrderByDescending(self, key_selector: Callable[[Any], Any]):
        """Return an OrderedSpaceList to allow .ThenBy(...) chaining."""
        return OrderedSpaceList(list(self), [(key_selector, True)])

    def OrderBy(self, key_selector: Callable[[Any], Any]):
        return OrderedSpaceList(list(self), [(key_selector, False)])

    def getSpaceByNumber(self, number):
        """
        Return the first space whose Number (or number) matches `number`.
        Behaves like the C# helper: tolerant to int/str types and returns None if not found.
        """
        if number is None:
            return None

        # try normalize requested number to int when possible
        try:
            req_int = int(number)
        except Exception:
            req_int = None
        req_str = str(number)

        for s in getattr(self, 'spaces', []) or []:
            s_num = getattr(s, 'Number', getattr(s, 'number', None))
            if s_num is None:
                continue

            # try integer comparison first
            try:
                if req_int is not None and int(s_num) == req_int:
                    return s
            except Exception:
                pass

            # fallback to string comparison
            try:
                if str(s_num) == req_str:
                    return s
            except Exception:
                pass

        return None

    # snake_case aliases
    order_by_descending = OrderByDescending
    order_by = OrderBy
    DriverSide = driver_side
    HelperSide = helper_side

    # utility
    def to_list(self):
        return list(self.spaces)

    def ToList(self):
        return self.to_list()

    def __iter__(self):
        return iter(self.spaces)

    def __len__(self):
        return len(self.spaces)

    def __getitem__(self, index):
        """Support indexing and slicing like a regular sequence.

        - If `index` is an int, return the Space at that position (may raise
          IndexError like a normal list).
        - If `index` is a slice, return a new SpaceList with the sliced items.
        """
        if isinstance(index, slice):
            return SpaceList(self.spaces[index])
        return self.spaces[index]

    def __repr__(self):
        return f"<SpaceList: {len(self.spaces)} spaces>"
