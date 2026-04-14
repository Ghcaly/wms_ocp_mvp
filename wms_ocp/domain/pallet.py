from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

@dataclass
class ItemPallet:
    sqEntrega: Optional[int] = None
    cdItem: Optional[int] = None
    qtUnVenda: Optional[int] = None
    sqMontagem: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

@dataclass
class Pallet:
    cdLado: Optional[str] = None
    nrBaiaGaveta: Optional[int] = None
    itens: List[ItemPallet] = field(default_factory=list)

    def add_item(self, item: ItemPallet) -> None:
        self.itens.append(item)

    def to_dict(self) -> Dict[str, Any]:
        data = {}
        if self.cdLado is not None:
            data["cdLado"] = self.cdLado
        if self.nrBaiaGaveta is not None:
            data["nrBaiaGaveta"] = self.nrBaiaGaveta
        data["itens"] = [it.to_dict() for it in self.itens]
        return data