from __future__ import annotations
from enum import IntEnum
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Iterable, Dict, Any
import csv
import copy
from pathlib import Path

class RuleConfigurationType(IntEnum):
    OrderPalletByPackageCodeOccupation = 0
    OrderPalletByCancha = 1
    BulkAllPallets = 2
    ReturnableAndDisposableSplitRuleDisabled = 3
    IsotonicTopPalletCustomOrderRule = 4
    ReduceVolumePallets = 5
    PercentageReductionInPalletOccupancy = 6
    QuantityOfPackagingOnSamePallet = 7
    ReassignmentOfNonPalletizedItems = 8
    SideBalanceRule = 9
    NotMountBulkPallets = 10
    PalletizeDetached = 14
    OrderPalletsByGroup = 16
    AssemblyProductsFromDifferentSubgroups = 17
    AllowEmptyBays = 18
    AllowVehicleWithoutBays = 19
    DistributeItemsOnEmptyPallets = 20
    MinimumQuantityOfSKUsToDistributeOnEmptyPallets = 21
    IncludeTopOfPallet = 22
    AdjustReassemblesAfterWater = 23
    UseBayLessThan35 = 24
    JoinPalletsWithLessThanOccupancy = 25
    OrderPalletByProductGroup = 26
    OrderProductsForAutoServiceMap = 27
    KegExclusivePallet = 28
    DistributeMixedRouteOnASCalculus = 29
    OrderByItemsSequence = 30
    AllowGroupingComplexLoads = 31
    MinimumVolumeInComplexLoads = 32
    QuantitySkuInComplexLoads = 33
    UseItemsExclusiveOfWarehouse = 34
    EnableSafeSideRule = 35
    JoinDisposables = 36
    LimitPackageGroups = 37
    SendCategoriesCantMixToBinpacking = 38
    Binpacking = 39
    MaxPackageGroups = 40
    OrderPalletByGroupSubGroupAndPackagingItem = 41
    OccupationAdjustmentToPreventExcessHeight = 42
    PalletEqualizationRule = 43
    ProductGroupSpecific = 44
    PercentOccupationMinByDivision = 45
    PercentOccupationMinBySelectionPalletDisassembly = 46


@dataclass
class RuleConfiguration:
    id: Optional[int] = None
    warehouse_id: Optional[int] = None
    warehouse_unb_code: Optional[str] = None
    warehouse_name: Optional[str] = None
    map_type: Optional[int] = None
    type: RuleConfigurationType = RuleConfigurationType.OrderPalletByPackageCodeOccupation
    value: Optional[bool] = None
    generic_value: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        # Fiel ao C#: retorna true apenas quando GenericValue pode ser parseado
        # como booleano true (equivalente a bool.TryParse(GenericValue, out result) && result).
        # Não faz fallback para `value`.
        if self.generic_value not in (None, ""):
            gv = str(self.generic_value).strip()
            return gv.lower() == "true"
        return False

    def set_active(self, active: bool):
        self.value = bool(active)

    def set_generic_value(self, generic_value: str):
        self.generic_value = generic_value

    def update(self, map_type: int, active: bool):
        self.map_type = map_type
        self.value = bool(active)

    def clone(self) -> "RuleConfiguration":
        return copy.deepcopy(self)

    def get_value(self) -> Optional[str]:
        if self.generic_value not in (None, ""):
            return self.generic_value
        t = self.get_value_type()
        # Fiel ao C#: quando não houver GenericValue, para tipos boolean
        # sempre retorna the literal "false" (independente de `value`).
        if t == "bool":
            return "false"
        if t == "int":
            return "0"
        return None

    def get_value_type(self) -> str:
        if self.type in BooleanRuleConfigurationTypes():
            return "bool"
        if self.type in IntegerRuleConfigurationTypes():
            return "int"
        return "string"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = int(self.type)
        d["type_name"] = self.type.name
        return d


def BooleanRuleConfigurationTypes() -> List[RuleConfigurationType]:
    return [
        RuleConfigurationType.OrderPalletByPackageCodeOccupation,
        RuleConfigurationType.OrderPalletByCancha,
        RuleConfigurationType.BulkAllPallets,
        RuleConfigurationType.ReturnableAndDisposableSplitRuleDisabled,
        RuleConfigurationType.IsotonicTopPalletCustomOrderRule,
        RuleConfigurationType.ReduceVolumePallets,
        RuleConfigurationType.ReassignmentOfNonPalletizedItems,
        RuleConfigurationType.SideBalanceRule,
        RuleConfigurationType.NotMountBulkPallets,
        RuleConfigurationType.OrderPalletsByGroup,
        RuleConfigurationType.AssemblyProductsFromDifferentSubgroups,
        RuleConfigurationType.AllowEmptyBays,
        RuleConfigurationType.AllowVehicleWithoutBays,
        RuleConfigurationType.DistributeItemsOnEmptyPallets,
        RuleConfigurationType.IncludeTopOfPallet,
        RuleConfigurationType.AdjustReassemblesAfterWater,
        RuleConfigurationType.UseBayLessThan35,
        RuleConfigurationType.OrderPalletByProductGroup,
        RuleConfigurationType.OrderProductsForAutoServiceMap,
        RuleConfigurationType.KegExclusivePallet,
        RuleConfigurationType.DistributeMixedRouteOnASCalculus,
        RuleConfigurationType.OrderByItemsSequence,
        RuleConfigurationType.AllowGroupingComplexLoads,
        RuleConfigurationType.UseItemsExclusiveOfWarehouse,
        RuleConfigurationType.EnableSafeSideRule,
        RuleConfigurationType.JoinDisposables,
        RuleConfigurationType.SendCategoriesCantMixToBinpacking,
        RuleConfigurationType.Binpacking,
        RuleConfigurationType.PalletizeDetached,
        RuleConfigurationType.LimitPackageGroups,
        RuleConfigurationType.OrderPalletByGroupSubGroupAndPackagingItem,
        RuleConfigurationType.OccupationAdjustmentToPreventExcessHeight,
        RuleConfigurationType.PalletEqualizationRule,
    ]


def IntegerRuleConfigurationTypes() -> List[RuleConfigurationType]:
    return [
        RuleConfigurationType.PercentageReductionInPalletOccupancy,
        RuleConfigurationType.QuantityOfPackagingOnSamePallet,
        RuleConfigurationType.MinimumQuantityOfSKUsToDistributeOnEmptyPallets,
        RuleConfigurationType.JoinPalletsWithLessThanOccupancy,
        RuleConfigurationType.MinimumVolumeInComplexLoads,
        RuleConfigurationType.QuantitySkuInComplexLoads,
        RuleConfigurationType.MaxPackageGroups,
        RuleConfigurationType.PercentOccupationMinByDivision,
        RuleConfigurationType.PercentOccupationMinBySelectionPalletDisassembly,
    ]


def load_rule_configurations_from_csv(csv_path: Path, filter_by_warehouse_unb_code: Optional[str] = None, map_type: Optional[int] = None) -> List[RuleConfiguration]:
    """Load and map CSV rows to RuleConfiguration objects.
    CSV expected with semicolon ';' delimiter and header:
    Id;WarehouseId;WarehouseUnbCode;WarehouseName;MapType;Type;Value;GenericValue

    When map_type is provided (e.g. 1 for Route), rows with that specific MapType take
    precedence over MapType=0 (global defaults): we load both and the specific one wins.
    When map_type is None, only MapType=0 is loaded (legacy behaviour).
    """
    # Load all matching rows (MapType 0 and specific), keyed by Type so specific overrides global
    rows_by_type: Dict[int, Any] = {}  # type_int -> row dict
    with csv_path.open(newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh, delimiter=';')
        for row in reader:
            if filter_by_warehouse_unb_code:
                if (row.get("WarehouseUnbCode") or "").strip() != filter_by_warehouse_unb_code:
                    continue

            try:
                row_map_type = int(row.get("MapType") or 0)
            except Exception:
                row_map_type = 0

            if map_type is not None:
                # Accept MapType=0 (global) and the specific MapType; specific wins
                if row_map_type not in (0, map_type):
                    continue
            else:
                # Legacy: only MapType=0
                if row_map_type != 0:
                    continue

            try:
                type_int = int(row.get("Type") or 0)
            except Exception:
                type_int = 0

            # Specific MapType overwrites global (MapType=0) for the same Type
            if row_map_type == 0 and type_int in rows_by_type:
                continue  # already have a more-specific row
            rows_by_type[type_int] = row

    configs: List[RuleConfiguration] = []
    for row in rows_by_type.values():
        # parse type safely (int -> enum)
        try:
            type_val = int(row.get("Type") or 0)
            try:
                rtype = RuleConfigurationType(type_val)
            except ValueError:
                rtype = RuleConfigurationType.OrderPalletByPackageCodeOccupation
        except Exception:
            rtype = RuleConfigurationType.OrderPalletByPackageCodeOccupation

        # parse booleans and ints
        try:
            wid = int(row.get("WarehouseId")) if row.get("WarehouseId") else None
        except Exception:
            wid = None
        try:
            mid = int(row.get("MapType")) if row.get("MapType") else None
        except Exception:
            mid = None

        # IMPORTANT: treat empty Value as None (nullable), matching C#'s bool? semantics
        valraw = (row.get("GenericValue") or "").strip()
        parsed_value: Optional[bool]
        if valraw == "":
            parsed_value = None
        else:
            vl = valraw.lower()
            if vl in ("true", "yes", "y"):
                parsed_value = True
            elif vl in ("false", "no", "n"):
                parsed_value = False
            else:
                parsed_value = vl

        cfg = RuleConfiguration(
            id=int(row.get("Id")) if row.get("Id") else None,
            warehouse_id=wid,
            warehouse_unb_code=(row.get("WarehouseUnbCode") or "").strip() or None,
            warehouse_name=(row.get("WarehouseName") or "").strip() or None,
            map_type=mid,
            type=rtype,
            value=parsed_value,
            generic_value=(row.get("GenericValue") or "").strip() or None,
            extra={k: v for k, v in row.items() if k not in ("Id", "WarehouseId", "WarehouseUnbCode", "WarehouseName", "MapType", "Type", "Value", "GenericValue")}
        )
        configs.append(cfg)
    return configs

def _pascal_to_camel(name: str) -> str:
    if not name:
        return name
    return name[0].lower() + name[1:]


# mapeamentos pontuais para nomes que diferem entre enum e config.json
_SETTING_NAME_OVERRIDES = {
    "UseBayLessThan35": "UseBaySmallerThan35",
    "JoinDisposables": "JoinDisposableContainers",
    "JoinPalletsWithLessThanOccupancy": "OccupationToJoinMountedSpaces",
    "OrderByItemsSequence": "OrderByItemsSequence",
    "OrderPalletByProductGroup": "OrderPalletByProductGroup",
    "OrderProductsForAutoServiceMap": "OrderProductsForAutoServiceMap",
    "OrderPalletByPackageCodeOccupation": "OrderPalletByPackageCodeOccupation",
    "OrderPalletByCancha": "OrderPalletByCancha",
    "GroupComplexLoads": "GroupComplexLoads",
    "LimitPackageGroups": "LimitPackageGroups",
    "PalletizeDetached": "PalletizeDetached",
    "MaxPackageGroups": "MaxPackageGroups",
    "UseItemsExclusiveOfWarehouse": "UseItemsExclusiveOfWarehouse",
    "EnableSafeSideRule": "EnableSafeSideRule",
    "PalletEqualizationRule": "PalletEqualizationRule",
    "OccupationAdjustmentToPreventExcessHeight": "OccupationAdjustmentToPreventExcessHeight",
    "PercentOccupationMinByDivision": "PercentOccupationMinByDivision",
    "PercentOccupationMinBySelectionPalletDisassembly": "PercentOccupationMinBySelectionPalletDisassembly",
    "QuantityOfPackagingOnSamePallet": "QuantityOfPackagingOnSamePallet",
    "MinimumQuantityOfSKUsToDistributeOnEmptyPallets": "MinimumQuantityOfSKUsToDistributeOnEmptySpaces",
    "MinimumVolumeInComplexLoads": "MinimumVolumeInComplexLoads",
    "QuantitySkuInComplexLoads": "QuantitySkuInComplexLoads",
    "Binpacking": "Binpacking",
    "SendCategoriesCantMixToBinpacking": "SendCategoriesCantMixToBinpacking",
    "ReduceVolumePallets": "ReduceVolumePallets",
    "PercentageReductionInPalletOccupancy": "PercentageReductionInPalletOccupancy",
    # adicione outros overrides conforme necessário
}


def build_settings_for_unb_code(warehouse_unb_code: str, csv_path: Path = None, map_type: Optional[int] = None) -> Dict[str, Any]:
    """
    Carrega `csv_path`, filtra por `warehouse_unb_code` e monta um dict `Settings`.
    - Booleans -> Python bool
    - Integers -> int
    - Generic string values preserved for string types

    map_type: when provided (e.g. 1=Route, 2=AS), MapType-specific rows override MapType=0 globals.
    """
    if not csv_path:
        csv_path = Path(__file__).parent.parent / 'database' / 'ruleconfiguration_12012026.csv'

    configs = load_rule_configurations_from_csv(csv_path, filter_by_warehouse_unb_code=warehouse_unb_code, map_type=map_type)
    settings: Dict[str, Any] = {}

    for cfg in configs:
        enum_name = cfg.type.name  # ex: 'EnableSafeSideRule'
        key = _SETTING_NAME_OVERRIDES.get(enum_name, _pascal_to_camel(enum_name))

        value_type = cfg.get_value_type()  # 'bool' | 'int' | 'string'
        raw_generic = cfg.generic_value if cfg.generic_value not in (None, "") else None
        # prefer generic_value when presente, senão use cfg.value (bool) or default
        parsed_value: Any = None

        if raw_generic is not None:
            rv = str(raw_generic).strip()
            if value_type == "bool":
                parsed_value = rv.lower() in ("1", "true", "yes", "y")
            elif value_type == "int":
                try:
                    parsed_value = int(rv)
                except Exception:
                    try:
                        parsed_value = int(float(rv))
                    except Exception:
                        parsed_value = 0
            else:
                parsed_value = rv
        else:
            if value_type == "bool":
                parsed_value = bool(cfg.value) if cfg.value is not None else False
            elif value_type == "int":
                try:
                    parsed_value = int(cfg.value) if cfg.value is not None else 0
                except Exception:
                    parsed_value = 0
            else:
                parsed_value = cfg.generic_value if cfg.generic_value not in (None, "") else None

        settings[key] = parsed_value

    return settings
