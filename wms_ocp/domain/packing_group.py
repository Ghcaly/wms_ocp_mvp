from __future__ import annotations
from typing import Optional, Any
from datetime import datetime


class PackingGroup:
    """Python port of the C# PackingGroup entity.

    This mirrors the properties and BuildWith/Update methods from the C# class.
    """

    def __init__(
        self,
        Code: Optional[int] = None,
        PackingCode: int = 0,
        PackingName: str = "",
        GroupCode: int = 0,
        SubGroupCode: int = 0,
        ProductTypeCode: int = 0,
        ProductTypeName: str = "",
        IsGlobal: Optional[bool] = None,
        IsRegional: Optional[bool] = None,
        WarehouseUnbCode: Optional[str] = None,
        WmsId: Optional[str] = None,
        NewPackingCode: Optional[int] = None,
        NewGroupCode: Optional[int] = None,
        NewSubGroupCode: Optional[int] = None,
        NewProductTypeCode: Optional[int] = None,
        ZoneCountryId: Optional[int] = None,
        WarehouseId: Optional[int] = None,
        CatalogId: Optional[int] = None,
        Catalog: Any = None,
        ZoneCountry: Any = None,
        Warehouse: Any = None,
        DisabledDate: Optional[datetime] = None,
        # optional snake_case overrides
        code: Optional[int] = None,
        packing_code: Optional[int] = None,
        packing_name: Optional[str] = None,
    ):
        self._Code = code if code is not None else Code
        self._PackingCode = int(packing_code) if packing_code is not None else int(PackingCode)
        self._PackingName = packing_name if packing_name is not None else PackingName
        self._GroupCode = int(GroupCode)
        self._SubGroupCode = int(SubGroupCode)
        self._ProductTypeCode = int(ProductTypeCode)
        self._ProductTypeName = ProductTypeName
        self._IsGlobal = IsGlobal
        self._IsRegional = IsRegional
        self._WarehouseUnbCode = WarehouseUnbCode
        self._WmsId = WmsId
        self._NewPackingCode = NewPackingCode
        self._NewGroupCode = NewGroupCode
        self._NewSubGroupCode = NewSubGroupCode
        self._NewProductTypeCode = NewProductTypeCode
        self._ZoneCountryId = ZoneCountryId
        self._WarehouseId = WarehouseId
        self._CatalogId = CatalogId
        self._Catalog = Catalog
        self._ZoneCountry = ZoneCountry
        self._Warehouse = Warehouse
        self._DisabledDate = DisabledDate

    # PascalCase properties mapping to private fields
    @property
    def Code(self) -> Optional[int]:
        return getattr(self, "_Code", None)

    @Code.setter
    def Code(self, v: Optional[int]):
        self._Code = v

    @property
    def PackingCode(self) -> int:
        return getattr(self, "_PackingCode", 0)

    @PackingCode.setter
    def PackingCode(self, v: int):
        self._PackingCode = int(v)

    @property
    def PackingName(self) -> str:
        return getattr(self, "_PackingName", "")

    @PackingName.setter
    def PackingName(self, v: str):
        self._PackingName = v

    @property
    def GroupCode(self) -> int:
        return getattr(self, "_GroupCode", 0)

    @GroupCode.setter
    def GroupCode(self, v: int):
        self._GroupCode = int(v)

    @property
    def SubGroupCode(self) -> int:
        return getattr(self, "_SubGroupCode", 0)

    @SubGroupCode.setter
    def SubGroupCode(self, v: int):
        self._SubGroupCode = int(v)

    @property
    def ProductTypeCode(self) -> int:
        return getattr(self, "_ProductTypeCode", 0)

    @ProductTypeCode.setter
    def ProductTypeCode(self, v: int):
        self._ProductTypeCode = int(v)

    # Backwards-compatible alias expected by some C#-ported code
    @property
    def TypeCode(self) -> int:
        return self.ProductTypeCode

    @TypeCode.setter
    def TypeCode(self, v: int):
        self.ProductTypeCode = int(v)

    @property
    def type_code(self) -> int:
        return self.TypeCode

    @property
    def ProductTypeName(self) -> str:
        return getattr(self, "_ProductTypeName", "")

    @ProductTypeName.setter
    def ProductTypeName(self, v: str):
        self._ProductTypeName = v

    @property
    def DisabledDate(self) -> Optional[datetime]:
        return getattr(self, "_DisabledDate", None)

    @DisabledDate.setter
    def DisabledDate(self, v: Optional[datetime]):
        self._DisabledDate = v

    # snake_case convenience aliases
    @property
    def packing_code(self) -> int:
        return self.PackingCode

    @property
    def packing_name(self) -> str:
        return self.PackingName

    @property
    def group_code(self) -> int:
        return self.GroupCode

    @property
    def sub_group_code(self) -> int:
        return self.SubGroupCode

    @property
    def product_type_code(self) -> int:
        return self.ProductTypeCode

    @property
    def disabled_date(self) -> Optional[datetime]:
        return self.DisabledDate

    @property
    def Description(self) -> str:
        pack_code = self.NewPackingCode if self.NewPackingCode is not None else self.PackingCode
        prod_type = self.NewProductTypeCode if self.NewProductTypeCode is not None else self.ProductTypeCode
        return f"{pack_code} - {self.PackingName} (Tipo: {prod_type} - {self.ProductTypeName})"

    @property
    def IsValid(self) -> bool:
        # Fiel à intenção do C#: válido quando códigos existem e não são zeros/empty
        return bool(self.GroupCode) and bool(self.SubGroupCode)

    @property
    def is_valid(self) -> bool:
        return self.IsValid
    
    @classmethod
    def BuildWith(cls, packingGroupCommand: Any) -> "PackingGroup":
        # packingGroupCommand expected to have attributes used in C# BuildWith
        pg = cls(
            Code=getattr(packingGroupCommand, "Code", None),
            GroupCode=int(getattr(packingGroupCommand, "GroupCode", 0)),
            PackingCode=int(getattr(packingGroupCommand, "PackingCode", 0)),
            PackingName=getattr(packingGroupCommand, "PackingName", ""),
            ProductTypeCode=int(getattr(packingGroupCommand, "ProductTypeCode", 0)),
            ProductTypeName=getattr(packingGroupCommand, "ProductTypeName", ""),
            SubGroupCode=int(getattr(packingGroupCommand, "SubGroupCode", 0)),
            IsGlobal=getattr(packingGroupCommand, "IsGlobal", None),
            IsRegional=getattr(packingGroupCommand, "IsRegional", None),
            WarehouseUnbCode=getattr(packingGroupCommand, "WarehouseUnbCode", None),
            WmsId=getattr(packingGroupCommand, "WmsId", None),
            ZoneCountryId=getattr(packingGroupCommand, "ZoneCountryId", None),
            WarehouseId=getattr(packingGroupCommand, "WarehouseId", None),
            NewPackingCode=int(getattr(packingGroupCommand, "PackingCode", 0)),
            NewGroupCode=getattr(packingGroupCommand, "GroupCode", None),
            NewSubGroupCode=getattr(packingGroupCommand, "SubGroupCode", None),
            NewProductTypeCode=getattr(packingGroupCommand, "ProductTypeCode", None),
            CatalogId=getattr(packingGroupCommand, "CatalogId", None),
            DisabledDate=None if getattr(packingGroupCommand, "Active", True) else datetime.utcnow(),
        )
        return pg

    def Update(self, packingGroupCommand: Any):
        self.GroupCode = int(getattr(packingGroupCommand, "GroupCode", self.GroupCode))
        self.PackingCode = int(getattr(packingGroupCommand, "PackingCode", self.PackingCode))
        self.PackingName = getattr(packingGroupCommand, "PackingName", self.PackingName)
        self.ProductTypeCode = int(getattr(packingGroupCommand, "ProductTypeCode", self.ProductTypeCode))
        self.ProductTypeName = getattr(packingGroupCommand, "ProductTypeName", self.ProductTypeName)
        self.SubGroupCode = int(getattr(packingGroupCommand, "SubGroupCode", self.SubGroupCode))
        self.IsGlobal = getattr(packingGroupCommand, "IsGlobal", self.IsGlobal)
        self.IsRegional = getattr(packingGroupCommand, "IsRegional", self.IsRegional)
        self.ZoneCountryId = getattr(packingGroupCommand, "ZoneCountryId", self.ZoneCountryId)
        self.WarehouseUnbCode = getattr(packingGroupCommand, "WarehouseUnbCode", self.WarehouseUnbCode)
        self.WarehouseId = getattr(packingGroupCommand, "WarehouseId", self.WarehouseId)
        self.WmsId = getattr(packingGroupCommand, "WmsId", self.WmsId)
        self.NewPackingCode = getattr(packingGroupCommand, "PackingCode", self.NewPackingCode)
        self.NewGroupCode = getattr(packingGroupCommand, "GroupCode", self.NewGroupCode)
        self.NewSubGroupCode = getattr(packingGroupCommand, "SubGroupCode", self.NewSubGroupCode)
        self.NewProductTypeCode = getattr(packingGroupCommand, "ProductTypeCode", self.NewProductTypeCode)
        self.CatalogId = getattr(packingGroupCommand, "CatalogId", self.CatalogId)
        self.DisabledDate = None if getattr(packingGroupCommand, "Active", True) else datetime.utcnow()

    # pythonic aliases
    @classmethod
    def build_with(cls, packingGroupCommand: Any) -> "PackingGroup":
        return cls.BuildWith(packingGroupCommand)

    def update(self, packingGroupCommand: Any):
        return self.Update(packingGroupCommand)

