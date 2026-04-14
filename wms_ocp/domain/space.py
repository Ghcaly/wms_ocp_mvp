from __future__ import annotations
from decimal import Decimal
from typing import Optional, Any


class Space:
    """
    Python port of ISpace from C#.
    Represents a space/bay in a vehicle where products can be placed.
    """
    
    def __init__(
        self,
        Id: int = 0,
        Size: Decimal = Decimal(0),
        Number: int = 0,
        Side: str = "",
        Blocked: bool = False,
        # snake_case overrides
        id: Optional[int] = None,
        size: Optional[Decimal] = None,
        number: Optional[int] = None,
        side: Optional[str] = None,
        blocked: Optional[bool] = None,
    ):
        self._id = int(id) if id is not None else int(Id)
        self._size = Decimal(size) if size is not None else Decimal(Size)
        self._number = int(number) if number is not None else int(Number)
        self._side = side if side is not None else Side
        self._blocked = bool(blocked) if blocked is not None else bool(Blocked)
        self._balanced = False
    
    # --- PascalCase properties (C# compatibility) ---
    @property
    def Id(self) -> int:
        return self._id
    
    @Id.setter
    def Id(self, v: int):
        self._id = int(v)
    
    @property
    def Size(self) -> Decimal:
        return self._size
    
    @Size.setter
    def Size(self, v: Decimal):
        self._size = Decimal(v)
    
    @property
    def Number(self) -> int:
        return self._number
    
    @Number.setter
    def Number(self, v: int):
        self._number = int(v)
    
    @property
    def Side(self) -> str:
        return self._side
    
    @Side.setter
    def Side(self, v: str):
        self._side = v
    
    @property
    def Blocked(self) -> bool:
        return self._blocked
    
    @Blocked.setter
    def Blocked(self, v: bool):
        self._blocked = bool(v)
    
    # --- snake_case aliases (Python style) ---
    @property
    def id(self) -> int:
        return self._id
    
    @id.setter
    def id(self, v: int):
        self._id = int(v)
    
    @property
    def size(self) -> Decimal:
        return self._size
    
    @size.setter
    def size(self, v: Decimal):
        self._size = Decimal(v)
    
    @property
    def number(self) -> int:
        return self._number
    
    @number.setter
    def number(self, v: int):
        self._number = int(v)
    
    @property
    def side(self) -> str:
        return self._side
    
    @property
    def sideDesc(self) -> str:
        return chr(int(str(self.Side).strip())).upper()
    
    @side.setter
    def side(self, v: str):
        self._side = v
    
    @property
    def blocked(self) -> bool:
        return self._blocked
    
    @blocked.setter
    def blocked(self, v: bool):
        self._blocked = bool(v)
    
    # --- Helper methods (C# interface) ---
    def IsBlocked(self) -> bool:
        """Check if space is blocked (C# style)"""
        return self.Blocked
    
    def is_blocked(self) -> bool:
        """Check if space is blocked (Python style)"""
        return self.IsBlocked()
    
    def SetBlocked(self, blocked: bool):
        """Set blocked status (C# style)"""
        self.Blocked = blocked
    
    def set_blocked(self, blocked: bool):
        """Set blocked status (Python style)"""
        self.SetBlocked(blocked)
    
    @property
    def Balanced(self) -> bool:
        return bool(self._balanced)

    @Balanced.setter
    def Balanced(self, v: bool):
        self._balanced = bool(v)

    def SetBalanced(self):
        """Compat com C#: marca o espaço como balanceado."""
        self.Balanced = True

    def set_balanced(self):
        """snake_case alias."""
        return self.SetBalanced()
    
    def IsDriverSide(self) -> bool:
        """Check if this space is on the driver side (C# style)"""
        side = str(self.Side).strip()
        if side.isdigit():
            return chr(int(side)).upper() in ("D", "M")
        return side.upper() in ("M", "D", "DRIVER", "MOTORISTA")

    def is_driver_side(self) -> bool:
        """Check if this space is on the driver side (Python style)"""
        return self.IsDriverSide()

    def IsHelperSide(self) -> bool:
        """Check if this space is on the helper side (C# style)"""
        side = str(self.Side).strip()
        if side.isdigit():
            return chr(int(side)).upper() in ("A", "H")
        return side.upper() in ("A", "H", "HELPER", "AJUDANTE")
    
    def is_helper_side(self) -> bool:
        """Check if this space is on the helper side (Python style)"""
        return self.IsHelperSide()
    
    def __repr__(self):
        return f"Space(Id={self.Id}, Number={self.Number}, Side={self.Side}, Size={self.Size}, Blocked={self.Blocked})"
    
    def __str__(self):
        return f"Space #{self.Number} ({self.Side}) - Size: {self.Size}"


def NotBulk(mounted_spaces):
    """Filter out mounted spaces that are bulk (i.e., have any pallet container with bulk==True).

    - If passed a single MountedSpace-like object, returns a boolean (not bulk).
    - If passed an iterable, returns a list filtered to mounted spaces that are NOT bulk.
    """
    if mounted_spaces is None:
        return []

    # single instance
    if hasattr(mounted_spaces, 'get_products') or hasattr(mounted_spaces, 'products'):
        try:
            return not getattr(mounted_spaces, 'is_bulk', False)
        except Exception:
            return True

    try:
        return [m for m in mounted_spaces if not getattr(m, 'is_bulk', False)]
    except Exception:
        return []


def NotBlocked(mounted_spaces):
    """Filter out mounted spaces that are blocked.

    - If passed a single MountedSpace-like object, returns a boolean (not blocked).
    - If passed an iterable, returns a list filtered to mounted spaces that are NOT blocked.
    """
    if mounted_spaces is None:
        return []

    # single instance
    if hasattr(mounted_spaces, 'get_products') or hasattr(mounted_spaces, 'products'):
        return not bool(getattr(getattr(mounted_spaces, 'space', None), 'blocked', False) or getattr(mounted_spaces, 'blocked', False))

    try:
        return [m for m in mounted_spaces if not (getattr(getattr(m, 'space', None), 'blocked', False) or getattr(m, 'blocked', False))]
    except Exception:
        return []


def NotChopp(mounted_spaces):
    """Return mounted spaces that are NOT chopp (exclude chopp/keg pallets).

    - If passed a single MountedSpace-like object, returns a boolean (is not chopp).
    - If passed an iterable, returns a list filtered to mounted spaces that have no chopp products.
    """
    if mounted_spaces is None:
        return []

    def _is_chopp_ms(ms):
        prods = ms.get_products() if hasattr(ms, 'get_products') else getattr(ms, 'products', [])
        for p in prods:
            prod = getattr(p, 'product', p)
            if getattr(prod, 'is_chopp', False) or getattr(prod, 'is_chopp', False):
                return True
        return False

    # single instance
    if hasattr(mounted_spaces, 'get_products') or hasattr(mounted_spaces, 'products'):
        return not _is_chopp_ms(mounted_spaces)

    try:
        return [m for m in mounted_spaces if not _is_chopp_ms(m)]
    except Exception:
        return []