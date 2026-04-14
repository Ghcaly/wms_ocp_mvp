from __future__ import annotations
from copy import deepcopy
from datetime import datetime
import json
import logging
from typing import Any, Callable, Iterable, List, Optional, TYPE_CHECKING, Union
from decimal import Decimal
from types import SimpleNamespace

from ..domain.itemList import ItemList
from ..domain.mounted_product_list import MountedProductList
from ..adapters.logger_instance import logger
from ..domain.palletize_dto import PalletizeDto
from ..domain.operations import DomainOperations
from ..domain.factor_converter import FactorConverter
from .order import Order
from .item import Item
from .mounted_product import MountedProduct
from .mounted_space import MountedSpace
from .mounted_space_list import MountedSpaceList
from .space import Space
from .product import Product
from pathlib import Path

class Context:
    """
    Base Context port of C# RuleContext.
    Keeps a minimal but practical surface used by migrated rules:
      - Orders, Spaces, MountedSpaces, Settings
      - snapshot helpers (CreateSnapshot / From)
      - GetAllSpaces
      - SwitchProducts / switch_products (aliases)
      - basic settings accessor get_setting
    Rules expect PascalCase names in many ports; this class exposes both PascalCase and pythonic aliases
    for common operations to maximize compatibility.
    """

    def __init__(
        self,
        orders: Optional[Iterable["Order"]] = None,
        spaces: Optional[Iterable["Space"]] = None,
        mounted_spaces: Optional[Iterable["MountedSpace"]] = None,
        settings: Optional[dict] = None,
        domain_operations: Optional[Any] = None,
        factor_converter: Optional[Any] = None,
        json_path: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
    ):
        self._orders: List["Order"] = list(orders) if orders is not None else []
        self._spaces: List["Space"] = list(spaces) if spaces is not None else []
        self._mounted_spaces: List["MountedSpace"] = list(mounted_spaces) if mounted_spaces is not None else []
        # private backing fields for settings and helpers
        self._settings: dict = dict(settings) if settings is not None else {}
        self._domain_operations = DomainOperations()
        self._factor_converter = FactorConverter()
        self._status: Optional[str] = None
        self._map_number: Optional[int] = None
        self._delivery_date = None
        self._kind = "Context"
        self._snapshot: Optional["Context"] = None
        self._palletize_dto: Optional[PalletizeDto] = None
        self._mounted_space_filter: Callable = lambda ms: True

        # Se um caminho do config foi fornecido, carrega as configurações
        if config_path:
            self._load_from_config(config_path)
        
        # Se um caminho do JSON foi fornecido, carrega os dados
        if json_path:
            self.load_json_input(json_path)

        # self._ensure_all_mounted_spaces()

    # --- PascalCase compatibility properties (map to private fields) ---
    @property
    def PalletizeDto(self) -> Optional[PalletizeDto]:
        return self._palletize_dto

    @PalletizeDto.setter
    def PalletizeDto(self, v: Optional[PalletizeDto]):
        self._palletize_dto = v

    @property
    def palletize_dto(self) -> Optional[PalletizeDto]:
        return self.PalletizeDto

    @palletize_dto.setter
    def palletize_dto(self, v: Optional[PalletizeDto]):
        self.PalletizeDto = v
        
    @property
    def Settings(self) -> dict:
        return self._settings

    @Settings.setter
    def Settings(self, v: dict):
        self._settings = dict(v) if v is not None else {}

    @property
    def DomainOperations(self) -> Optional[Any]:
        return self._domain_operations

    @DomainOperations.setter
    def DomainOperations(self, v: Optional[Any]):
        self._domain_operations = v

    @property
    def FactorConverter(self) -> Optional[Any]:
        return self._factor_converter

    @FactorConverter.setter
    def FactorConverter(self, v: Optional[Any]):
        self._factor_converter = v

    @property
    def Status(self) -> Optional[str]:
        return self._status

    @Status.setter
    def Status(self, v: Optional[str]):
        self._status = v

    @property
    def MapNumber(self) -> Optional[int]:
        return self._map_number

    @MapNumber.setter
    def MapNumber(self, v: Optional[int]):
        self._map_number = v

    @property
    def DeliveryDate(self):
        return self._delivery_date

    @DeliveryDate.setter
    def DeliveryDate(self, v):
        self._delivery_date = v

    @property
    def Snapshot(self) -> Optional["Context"]:
        """C#: Snapshot property - returns a snapshot of the context state"""
        return self._snapshot

    @Snapshot.setter
    def Snapshot(self, v: Optional["Context"]):
        self._snapshot = v

    # Kind property (new): expose the private _kind with PascalCase and snake_case accessors
    @property
    def Kind(self) -> Optional[str]:
        return self._kind

    @Kind.setter
    def Kind(self, v: Optional[str]):
        self._kind = v

    @property
    def kind(self) -> Optional[str]:
        return self.Kind

    @kind.setter
    def kind(self, v: Optional[str]):
        self.Kind = v

    @property
    def delivery_date(self):
        return self.DeliveryDate

    @delivery_date.setter
    def delivery_date(self, v):
        self.DeliveryDate = v

    @property
    def snapshot(self) -> Optional["Context"]:
        return self.Snapshot

    @snapshot.setter
    def snapshot(self, v: Optional["Context"]):
        self.Snapshot = v

    # Expose PascalCase collection properties for compatibility
    @property
    def Orders(self) -> List["Order"]:
        return self._orders

    @Orders.setter
    def Orders(self, value: Iterable["Order"]):
        self._orders = list(value) if value is not None else []

    def SetQuantityOfPalletsNeededOnOrder(self, order, value):
        """Compatibility helper used by migrated rules.

        Sets the pallets-needed value on the given order. Mirrors C# helper used
        by NumberOfPalletsRule.
        """
        # delegate to order API
        if hasattr(order, 'SetQuantityOfPalletsNeeded'):
            order.SetQuantityOfPalletsNeeded(value)
        else:
            # fallback: set attribute directly
            try:
                order.QuantityOfPalletsNeeded = value
            except Exception:
                setattr(order, 'QuantityOfPalletsNeeded', value)

    # snake_case alias
    def set_quantity_of_pallets_needed_on_order(self, order, value):
        return self.SetQuantityOfPalletsNeededOnOrder(order, value)

    # @property
    # def Spaces(self) -> List["Space"]:
    #     return self._spaces

    @property
    def Spaces(self) -> List["Space"]:
        """
        C#: _spaces.Concat(_mountedSpaces.Where(x => !x.GetProducts().Any()).Select(x => x.Space))
        Returns available spaces including spaces from empty mounted spaces.
        """
        # Get spaces from mounted spaces that have no products
        empty_mounted_spaces = [ms.Space for ms in self._mounted_spaces if not ms.GetProducts()]
        
        # Combine with unused spaces
        all_spaces = list(self._spaces) + empty_mounted_spaces
        
        # Sort by Number ASC, then A (Helper) before M (Driver) for same bay number.
        # IsDriverSide() = True for M, False for A → (Number, IsDriverSide) puts A before M.
        return sorted(all_spaces, key=lambda x: (x.Number, x.IsDriverSide()))

    @Spaces.setter
    def Spaces(self, value: Iterable["Space"]):
        self._spaces = list(value) if value is not None else []

    @property
    def MountedSpaces(self) -> "MountedSpaceList":
        return MountedSpaceList(self._mounted_spaces)

    @MountedSpaces.setter
    def MountedSpaces(self, value: Iterable["MountedSpace"]):
        self._mounted_spaces = list(value) if value is not None else []

    @property
    def Pallets(self) -> List[Any]:
        """Compatibility: collect pallet/container-like objects from mounted spaces."""
        pallets: List[Any] = []
        for m in self._mounted_spaces:
            # prefer explicit Containers list if present
            conts = getattr(m, "Containers", None)
            if conts:
                pallets.extend(conts)
                continue
            # some MountedSpace implementations expose GetContainers / Products
            if hasattr(m, "GetContainers"):
                try:
                    pallets.extend(m.GetContainers() or [])
                    continue
                except Exception:
                    pass
            prods = getattr(m, "Products", None)
            if prods:
                # treat the mounted space itself as a pallet-like entity
                pallets.append(m)
        return pallets

    @property
    def pallets(self) -> List[Any]:
        return self.Pallets
    
    # def ReattachOriginalOrdersToMountedProducts(self) -> None:
    #     """
    #     Best-effort: reattach original per-item order/map info to MountedProduct
    #     instances using `item._sources` metadata when present.
    #     This mirrors the helper added by the port to allow output mappers to
    #     emit original MapNumber/DeliverySequence after rules that merged orders.
    #     """
    #     try:
    #         prods = self.GetAllProducts() or []
    #     except Exception:
    #         prods = []

    #     for mp in list(prods or []):
    #         try:
    #             item = getattr(mp, 'Item', None)
    #             if item is None:
    #                 continue
    #             sources = getattr(item, '_sources', None)
    #             if not sources:
    #                 continue
    #             first = None
    #             try:
    #                 first = sources[0]
    #             except Exception:
    #                 first = None
    #             if first is None:
    #                 continue

    #             if hasattr(first, 'Items'):
    #                 try:
    #                     mp.Order = first
    #                     mp.MapNumber = getattr(first, 'MapNumber', getattr(first, 'map_number', None))
    #                     continue
    #                 except Exception:
    #                     pass

    #             if isinstance(first, dict):
    #                 mapnum = first.get('MapNumber') or first.get('Map') or first.get('mapNumber') or first.get('map')
    #                 delivery = first.get('DeliveryOrder') or first.get('Delivery') or first.get('deliveryOrder')
    #                 found = None
    #                 if mapnum is not None:
    #                     for o in list(self.Orders or []):
    #                         try:
    #                             if str(getattr(o, 'MapNumber', getattr(o, 'map_number', None))) == str(mapnum):
    #                                 found = o
    #                                 break
    #                         except Exception:
    #                             continue
    #                 if not found and delivery is not None:
    #                     for o in list(self.Orders or []):
    #                         try:
    #                             if int(getattr(o, 'DeliveryOrder', getattr(o, 'delivery_order', -9999))) == int(delivery):
    #                                 found = o
    #                                 break
    #                         except Exception:
    #                             continue
    #                 if found is not None:
    #                     try:
    #                         mp.Order = found
    #                         mp.MapNumber = getattr(found, 'MapNumber', getattr(found, 'map_number', None))
    #                     except Exception:
    #                         pass
    #                     continue

    #             if isinstance(first, int):
    #                 for o in list(self.Orders or []):
    #                     try:
    #                         if int(getattr(o, 'DeliveryOrder', getattr(o, 'delivery_order', -9999))) == int(first):
    #                             mp.Order = o
    #                             mp.MapNumber = getattr(o, 'MapNumber', getattr(o, 'map_number', None))
    #                             break
    #                     except Exception:
    #                         continue
    #         except Exception:
    #             continue

    # def reattach_original_orders_to_mounted_products(self) -> None:
    #     return self.ReattachOriginalOrdersToMountedProducts()
    
    def load_json_input(self, input_source: Any) -> None:
        """Load input data (dict or path to JSON) and populate Context.Orders and their Items.

        The function accepts either a parsed JSON dict or a file path (str / Path). It will:
        - set self.MapNumber (from root Number when present)
        - populate self.Orders with `Order` instances
        - each Order will receive Item instances (with Amount, DetachedAmount, UnitAmount)

        This mirrors the input structure used by the provided example `input.json`.
        """
        # load JSON if a path/string provided
        data = None
        if isinstance(input_source, (str, bytes)):
            with open(input_source, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        elif isinstance(input_source, dict):
            data = input_source
        else:
            # allow file-like objects
            try:
                data = json.load(input_source)
            except Exception:
                raise ValueError("Unsupported input_source for load_json_input")

        # set some top-level context fields
        root_number = data.get("Number")
        try:
            # prefer numeric map number when possible
            self.MapNumber = int(root_number) if root_number is not None else None
        except Exception:
            self.MapNumber = str(root_number) if root_number is not None else None

        delivery_date = data.get("DeliveryDate")
        if delivery_date:
            try:
                self.DeliveryDate = datetime.fromisoformat(delivery_date)
            except Exception:
                self.DeliveryDate = delivery_date

        orders_in = data.get("Orders", []) or []
        orders_out: List["Order"] = []
        for idx, o in enumerate(orders_in, start=1):
            # derive basic identifiers
            delivery_order = o.get("RoadShow") if o.get("RoadShow") is not None else idx
            identifier = idx

            order_obj = Order(DeliveryOrder=int(delivery_order), Identifier=int(identifier))

            # map Cross info
            cross = o.get("Cross", {}) or {}
            map_number = cross.get("MapNumber")
            support_point = cross.get("SupportPoint")
            license_plate = None
            try:
                vehicle = cross.get("Vehicle", {}) if cross is not None else {}
                license_plate = vehicle.get("Plate")
            except Exception:
                license_plate = None

            if map_number is not None:
                try:
                    order_obj.MapNumber = str(map_number)
                except Exception:
                    order_obj.MapNumber = map_number
            if support_point is not None:
                order_obj.SupportPoint = support_point
            if license_plate is not None:
                order_obj.LicensePlate = license_plate

            # Extrai código do cliente de várias formas possíveis para robustez
            client = None
            client_block = o.get("Client", None)
            if isinstance(client_block, dict):
                client = client_block.get('Code') or client_block.get('code') or client_block.get('Customer') or client_block.get('customer')
            elif client_block is not None:
                # pode ser string/number direto
                client = client_block
            # fallbacks comuns
            client = client or o.get('ClientCode') or o.get('Customer') or o.get('CustomerCode') or o.get('client')
            # debug: show what was found for client in the input
            try:
                print(f"[load_json_input] order_index={idx} client_block={client_block!r} resolved_client={client!r}")
            except Exception:
                logging.debug("Could not print client debug info for order %s", idx)
            
            client_code = None
            try:
                client_code = int(o.get("Client", {}).get("Code") or o.get("ClientCode") or o.get("client"))
            except Exception:
                client_code = None
                
            # build items
            items_in = o.get("Items", []) or []
            item_objs: List["Item"] = []
            for it in items_in:
                code_raw = it.get("Code")
                try:
                    code = int(code_raw)
                except Exception:
                    code = int(str(code_raw)) if code_raw is not None else 0

                qty = it.get("Quantity", {}) or {}
                sales = qty.get("Sales", 0) or 0
                detached = qty.get("Detached", 0) or 0
                unit = qty.get("Unit", 0) or 0

                # Passe tanto PascalCase quanto snake_case para garantir compatibilidade
                item_obj = Item(
                    Code=int(code),
                    Amount=int(sales),
                    OcpDefaultPerUni42=Decimal(0),
                    AmountRemaining=int(sales),
                    DetachedAmount=int(detached),
                    UnitAmount=int(unit),
                    Customer=str(client) if client is not None else None
                )

                # C#: newItem.AddDeliveryOrder(orderRequest.DeliveryOrder, item.Amount, item.DetachedAmount)
                # Popula os dicionários _delivery_orders e _delivery_orders_detached
                item_obj.AddDeliveryOrder(delivery_order, sales, detached)

                # popula ClientQuantity
                client_qty = self._parse_client_quantity(item_obj, o)

                if client_qty:
                    item_obj.ClientQuantity = client_qty
                    item_obj.client_quantity = client_qty
                else:
                    # fallback: atribui toda a quantidade ao cliente do pedido
                    qty = int(sales)
                    if client_code is not None:
                        item_obj.ClientQuantity = {client_code: qty}
                        item_obj.client_quantity = {client_code: qty}
                    else:
                        item_obj.ClientQuantity = {}
                        item_obj.client_quantity = {}
                        
                # attach product reference if available in the system (optional)
                # keep Product as None for now; consumers may set it later
                item_obj.Product = None

                item_objs.append(item_obj)

            order_obj.SetItems(item_objs)
            orders_out.append(order_obj)

        # assign to context
        self.Orders = orders_out
        
        # build and store PalletizeDto from raw payload for downstream mappers
        try:
            dto = self.build_palletize_dto_from_input(data)
            self.PalletizeDto = dto
        except Exception:
            # best-effort: ensure attribute exists even on error
            if self.PalletizeDto is None:
                self.PalletizeDto = PalletizeDto(original_payload=data or {})

        # --- Populate Spaces from input when available ---------------------------------
        # Prefer an explicit 'Spaces' array in the input; otherwise use root Vehicle.Bays
        spaces_in = data.get("Spaces") if data.get("Spaces") is not None else None
        if spaces_in is None:
            vehicle = data.get("Vehicle", {}) or {}
            spaces_in = vehicle.get("Bays", []) or []

        spaces_out: List[Space] = []
        for idx, s in enumerate(spaces_in, start=1):
            try:
                number_raw = s.get("Number", idx)
            except Exception:
                number_raw = idx
            try:
                number = int(number_raw)
            except Exception:
                # fallback to index if the provided number is not numeric
                number = idx

            # side can be provided as Side or SideId etc.
            side = s.get("Side", s.get("side", ""))

            # size/capacity may be provided as Size
            size_raw = s.get("Size", s.get("size", s.get("Capacity", 0)))
            try:
                size = Decimal(str(size_raw))
            except Exception:
                size = Decimal(0)

            # id: prefer explicit Id/Number, fallback to index
            try:
                sid = int(s.get("Id", s.get("MountedSpaceId", s.get("Number", number))))
            except Exception:
                sid = number

            space_obj = Space(id=sid, size=size, number=number, side=str(side))
            spaces_out.append(space_obj)

        # assign Spaces to context (use property setter)
        self.Spaces = spaces_out

    def _parse_client_quantity(self, item_json, order_json):
        # possíveis nomes no JSON: "ClientQuantity", "ClientQuantities", "Clients"
        cq = item_json.ClientQuantity
        if isinstance(cq, dict):
            # normalizar chaves/valores para int
            out = {}
            for k, v in cq.items():
                try:
                    out[int(k)] = int(v)
                except Exception:
                    try:
                        out[int(str(k).strip())] = int(v)
                    except Exception:
                        continue
            return out if out else None
        return None

    @property
    def SpacesEmpty(self):
        mounted_no_products = [
            ms.space
            for ms in self.MountedSpaces 
            if not ms.get_products()
        ]

        combined = list(self._spaces) + mounted_no_products

        combined.sort(key=lambda s: (s.number, s.is_driver_side()))

        return combined

    def _ensure_all_mounted_spaces(self):
        """Ensure there is a MountedSpace instance for every Space in context.spaces.

        Behaviour:
        - preserve existing mounted spaces (keep those that reference a Space)
        - ensure one mounted-space exists for every space in self._spaces (create if missing)
        - keep mounted-spaces that reference spaces not present in _spaces
        - normalize both snake_case and PascalCase accessors
        """
        try:
            # initialize backing list if missing
            mounted_list = getattr(self, "_mounted_spaces", None)
            if mounted_list is None:
                mounted_list = []
                self._mounted_spaces = mounted_list

            # keep PascalCase alias in sync
            if not getattr(self, "MountedSpaces", None):
                self.MountedSpaces = mounted_list

            # build lookup of existing mounted spaces by identity and by (Number,Side)
            existing_by_space_id = {}
            existing_by_number_side = {}
            for ms in list(mounted_list):
                ms_space = getattr(ms, "Space", None) or getattr(ms, "space", None)
                if ms_space is not None:
                    existing_by_space_id[id(ms_space)] = ms
                    key = (getattr(ms_space, "Number", getattr(ms_space, "number", None)),
                           getattr(ms_space, "Side", getattr(ms_space, "side", None)))
                    existing_by_number_side[key] = ms

            # ensure we have a mounted-space for every configured Space
            spaces = getattr(self, "_spaces", []) or []
            for sp in list(spaces):
                found = None
                # 1) identity match
                found = existing_by_space_id.get(id(sp))
                if not found:
                    # 2) number/side fallback
                    key = (getattr(sp, "Number", getattr(sp, "number", None)),
                           getattr(sp, "Side", getattr(sp, "side", None)))
                    found = existing_by_number_side.get(key)

                if not found:
                    # create a new MountedSpace bound to this space
                    ms = MountedSpace(space=sp)
                    try:
                        ms.Space = sp
                    except Exception:
                        setattr(ms, "Space", sp)
                    mounted_list.append(ms)
                    # update lookups
                    existing_by_space_id[id(sp)] = ms
                    existing_by_number_side[key] = ms

            # keep any mounted spaces that reference other spaces (no removal)
            # ensure backing fields and aliases are consistent
            self._mounted_spaces = mounted_list
            try:
                self.MountedSpaces = mounted_list
            except Exception:
                pass

        except Exception:
            # fail-safe: do not break rule execution if something unexpected happens
            pass

    def _load_from_config(self, config_path: Union[str, Path]) -> None:
        """Carrega configurações do arquivo de configuração do mapa"""
        try:
            path = Path(config_path)
            with open(path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Carrega configurações principais
            self.settings = config_data.get('Settings', {})
            
            # Converte strings boolean para bool
            self._convert_boolean_settings()
            # Converte strings numéricas para números (int ou float)
            self._convert_numeric_settings()
            
            # Carrega número do mapa se não foi definido
            if not self.MapNumber and 'MapNumber' in config_data:
                self.MapNumber = int(config_data['MapNumber'])
            
            # Carrega itens não paletizados
            self.not_palletized_items = config_data.get('NotPalletizedItems', [])
                        
            print(f"Configuração carregada: Mapa {self.MapNumber}")
            print(f"Settings carregadas: {len(self.settings)} configurações")
            print(f"Itens não paletizados: {len(self.not_palletized_items)} itens")
            
            
        except FileNotFoundError:
            print(f"Arquivo de configuração não encontrado: {config_path}")
        except json.JSONDecodeError as e:
            print(f"Erro ao decodificar configuração JSON: {e}")
        except Exception as e:
            print(f"Erro ao carregar configuração: {e}")
    
    def build_palletize_dto_from_input(self, data: dict) -> PalletizeDto:
        """Extract a PalletizeDto from the raw input JSON dict (best-effort).

        Returns a populated `PalletizeDto` with fields used by the mapper.
        """
        # determine spaces payload
        spaces_in = data.get("Spaces") if data.get("Spaces") is not None else None
        if spaces_in is None:
            vehicle_block = data.get("Vehicle", {}) or {}
            spaces_in = vehicle_block.get("Bays", []) or []

        # Warehouse / UnbCode
        unb, company, branch, filename,  = None, None, None, None
        wh = data.get("Warehouse") or {}
        if isinstance(wh, dict):
            unb = wh.get("UnbCode") or wh.get("unbCode") or wh.get("Branch")
            company = wh.get("Company") or wh.get("company")
            branch = wh.get("Branch") or wh.get("branch")
            filename = wh.get("FileName") or wh.get("fileName")


        # Vehicle plate
        vehicle_plate = None
        veh = data.get("Vehicle") or {}
        if isinstance(veh, dict):
            vehicle_plate = veh.get("LicensePlate") or veh.get("Plate") or veh.get("plate") or veh.get("licensePlate")
        vehicle_plate = vehicle_plate or (data.get("VehiclePlate") or data.get("vehiclePlate"))

        # request block
        req_block = data.get("Request") or {}
        if not vehicle_plate and isinstance(req_block, dict):
            vehicle_plate = req_block.get("vehiclePlate") or req_block.get("VehiclePlate")

        # Document number / type / delivery date / uniqueKey
        document_number = data.get("DocumentNumber") or data.get("documentNumber") or str(self.MapNumber)
        document_type = self.type_context(data.get("Type")) if data.get("Type") is not None else (data.get("DocumentType") or data.get("documentType"))
        delivery_date_raw = data.get("DeliveryDate") or data.get("deliveryDate") or (req_block.get("deliveryDate") if isinstance(req_block, dict) else None)
        unique_key = data.get("UniqueKey") or (req_block.get("UniqueKey") if isinstance(req_block, dict) else None)

        # normalize request dict with expected fields (best-effort)
        request_out = {}
        if isinstance(req_block, dict):
            request_out.update(req_block)
        request_out.setdefault("mapType", request_out.get("mapType") or request_out.get("MapType") or "Undefined")
        request_out.setdefault("fileName", filename)
        request_out.setdefault("unbCode", unb)
        request_out.setdefault("company", company)
        request_out.setdefault("branch", branch)
        request_out.setdefault("documentNumber", document_number)
        request_out.setdefault("vehiclePlate", vehicle_plate)
        request_out.setdefault("bays", None)
        request_out.setdefault("deliveryDate", delivery_date_raw)
        request_out.setdefault("orders", None)
        request_out.setdefault("uniqueKey", unique_key)

        dto = PalletizeDto(
            unb_code=unb,
            vehicle_plate=vehicle_plate,
            document_number=document_number,
            document_type=document_type,
            delivery_date=delivery_date_raw,
            request=request_out,
            original_payload=data,
            spaces_payload=spaces_in,
            unique_key = unique_key
        )

        return dto
    
    def _convert_boolean_settings(self):
        """Converte strings boolean das configurações para bool Python"""
        for key, value in list(self.settings.items()):
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in ('true', 'false'):
                    self.settings[key] = (normalized == 'true')


    def _convert_numeric_settings(self):
        """Converte strings numéricas nas configurações para int ou float.

        Regras:
        - tenta converter para int quando possível (ex: "42", "-3");
        - caso contrário tenta float (aceita vírgula como separador decimal);
        - mantém o valor original quando não for um número válido.
        """
        for key, value in list(self.settings.items()):
            if not isinstance(value, str):
                continue
            s = value.strip()
            if s == '':
                continue
            # já tratamos booleans no método anterior; ignora "true"/"false"
            low = s.lower()
            if low in ('true', 'false'):
                continue

            if ',' in value:
                continue

            # tenta int
            try:
                # aceitar sinais negativos
                if s.lstrip('+-').isdigit():
                    self.settings[key] = int(s)
                    continue
            except Exception:
                pass

            # tenta float (aceita vírgula como decimal)
            try:
                normalized = s.replace(',', '.')
                f = float(normalized)
                self.settings[key] = f
            except Exception:
                # mantém o valor original se não for numérico
                continue

    # --- Settings helpers -------------------------------------------------
    def get_setting(self, name: str, default: Optional[Any] = None) -> Any:
        return self.Settings.get(name, default)

    # --- Snapshot helpers ------------------------------------------------
    def CreateSnapshot(self, orders: Optional[Iterable["Order"]] = None, spaces: Optional[Iterable["Space"]] = None, mounted_spaces: Optional[Iterable["MountedSpace"]] = None, minimal: bool = True) -> "Context":
        """C#: CreateSnapshot - creates a deep copy snapshot with optional overrides"""

        if minimal:
            # reuse the lightweight implementation already present (CreateSnapshotMinimal)
            snap = self.CreateSnapshotMinimal(minimal=True)
            # apply optional overrides like the deepcopy version does
            if orders is not None:
                snap.Orders = list(orders)
            if spaces is not None:
                snap.Spaces = list(spaces)
            if mounted_spaces is not None:
                snap.MountedSpaces = list(mounted_spaces)
            self._snapshot = snap
            return snap
        
        snap = deepcopy(self)
        if orders is not None:
            snap.Orders = list(orders)
        if spaces is not None:
            snap.Spaces = list(spaces)
        if mounted_spaces is not None:
            snap.MountedSpaces = list(mounted_spaces)
        # Store snapshot in the property for later access
        self._snapshot = snap
        return snap

    def CreateSnapshotMinimal(self, minimal: bool = True):
        """
        Lightweight snapshot used by SnapshotRule.
        Copies only fields commonly read by rules (settings/converters reused).
        """
        snap = Context()
        snap._is_snapshot = True

        # reuse read-only helpers
        snap._settings = getattr(self, "_settings", None)
        snap._factor_converter = getattr(self, "_factor_converter", None)
        snap._operations = getattr(self, "_operations", None)

        # shallow copy spaces (keep minimal attributes)
        snap._spaces = self._spaces
        
        # shallow copy orders -> items with AmountRemaining and minimal Product info
        snap._orders = self._orders

        # shallow copy mounted spaces: Space minimal + Occupation
        snap._mounted_spaces = self._mounted_spaces
        self._snapshot = snap
        return snap

    def create_snapshot_minimal(self, minimal: bool = True):
        return self.CreateSnapshotMinimal(minimal)
    
    # --- pythonic aliases for common attributes ----------------------
    @property
    def orders(self) -> List["Order"]:
        return self._orders

    @orders.setter
    def orders(self, value: Iterable["Order"]):
        self._orders = list(value) if value is not None else []

    @property
    def spaces(self) -> List["Space"]:
        return self._spaces

    @spaces.setter
    def spaces(self, value: Iterable["Space"]):
        self._spaces = list(value) if value is not None else []

    @property
    def mounted_spaces(self) -> List["MountedSpace"]:
        return self._mounted_spaces

    @mounted_spaces.setter
    def mounted_spaces(self, value: Iterable["MountedSpace"]):
        self._mounted_spaces = list(value) if value is not None else []

    @property
    def settings(self) -> dict:
        return self.Settings

    @settings.setter
    def settings(self, value: dict):
        self.Settings = dict(value) if value is not None else {}

    @property
    def status(self) -> Optional[str]:
        return self.Status

    @status.setter
    def status(self, value: Optional[str]):
        self.Status = value

    @property
    def map_number(self) -> Optional[int]:
        return self.MapNumber

    @map_number.setter
    def map_number(self, value: Optional[int]):
        self.MapNumber = value

    @property
    def factor_converter(self) -> Optional[Any]:
        return self.FactorConverter

    @factor_converter.setter
    def factor_converter(self, v: Optional[Any]):
        self.FactorConverter = v

    @property
    def domain_operations(self) -> Optional[Any]:
        return self.DomainOperations

    @domain_operations.setter
    def domain_operations(self, v: Optional[Any]):
        self.DomainOperations = v

    # --- pythonic method aliases ------------------------------------
    def create_snapshot(self, orders: Optional[Iterable["Order"]] = None, spaces: Optional[Iterable["Space"]] = None, mounted_spaces: Optional[Iterable["MountedSpace"]] = None) -> "Context":
        return self.CreateSnapshot(orders=orders, spaces=spaces, mounted_spaces=mounted_spaces)

    def get_all_spaces(self) -> List["Space"]:
        return self.GetAllSpaces()

    def set_status(self, status: str):
        return self.SetStatus(status)

    def set_map_number(self, number: int):
        return self.SetMapNumber(number)

    def get_map_number(self) -> Optional[int]:
        return self.GetMapNumber()

    @staticmethod
    def From(context: "Context", orders: Iterable["Order"], spaces: Iterable["Space"], mounted_spaces: Iterable["MountedSpace"]) -> "Context":
        snap = deepcopy(context)
        snap.Orders = list(orders)
        snap.Spaces = list(spaces)
        snap.MountedSpaces = list(mounted_spaces)
        return snap

    @staticmethod
    def from_(context: "Context", orders: Iterable["Order"], spaces: Iterable["Space"], mounted_spaces: Iterable["MountedSpace"]) -> "Context":
        return Context.From(context, orders, spaces, mounted_spaces)

    # --- Basic collections access used by rules --------------------------
    def GetAllSpaces(self) -> List["Space"]:
        """
        Returns the configured vehicle/truck spaces plus the Spaces referenced by mounted-spaces.
        """
        return list(self.Spaces) + [m.Space for m in self._mounted_spaces]

    def GetSpacesWithEmptyMounted(self) -> List["Space"]:
        """Mimic C# RuleContext.Spaces: return _spaces plus Spaces of mounted-spaces that are empty.

        Behavior:
        - include all `self._spaces` (unmounted available spaces)
        - include `m.Space` for each mounted-space `m` where `m.GetProducts()` is empty
        - remove duplicates preserving order
        - sort by space.Number then by IsDriverSide() (like C# OrderBy/ThenBy)
        """
        combined: List["Space"] = []
        try:
            combined.extend(list(self._spaces))
        except Exception:
            try:
                combined.extend(list(self.Spaces))
            except Exception:
                pass

        # collect spaces from mounted spaces that have no products
        for m in list(getattr(self, '_mounted_spaces', []) or []):
            try:
                prods = None
                if hasattr(m, 'GetProducts'):
                    prods = m.GetProducts()
                else:
                    prods = getattr(m, 'Products', getattr(m, 'products', None)) or []
                if not prods:
                    sp = getattr(m, 'Space', getattr(m, 'space', None))
                    if sp is not None:
                        combined.append(sp)
            except Exception:
                continue

        # remove duplicates preserving order (by identity)
        unique: List["Space"] = []
        seen = set()
        for s in combined:
            try:
                sid = id(s)
            except Exception:
                sid = repr(s)
            if sid in seen:
                continue
            seen.add(sid)
            unique.append(s)

        # sort by Number then by IsDriverSide (attempt to call IsDriverSide or use attribute)
        def _space_key(sp):
            try:
                num = getattr(sp, 'Number', getattr(sp, 'number', 0)) or 0
            except Exception:
                num = 0
            try:
                is_driver = False
                attr = getattr(sp, 'IsDriverSide', getattr(sp, 'is_driver_side', None))
                if callable(attr):
                    is_driver = bool(attr())
                else:
                    is_driver = bool(attr)
            except Exception:
                is_driver = False
            return (int(num), bool(is_driver))

        try:
            return sorted(unique, key=_space_key)
        except Exception:
            return unique

    
    def GetDeliveriesSafeSide(self) -> List[tuple]:
        """
        C#: GetDeliveriesSafeSide - Returns list of (delivery_order, safe_side) tuples.
        
        Mirrors C# RuleContextExtensions.GetDeliveriesSafeSide:
        - Collects all products with amounts from mounted spaces
        - Gets unique items
        - Extracts DeliveryOrderSafeSide from each item
        
        Returns:
            List of (delivery_order, safe_side) tuples
        """
        # Get all mounted products with amounts
        mounted_products = []
        for ms in self._mounted_spaces:
            if hasattr(ms, 'GetProducts'):
                products = ms.GetProducts()
                # Filter products with amount
                for p in products:
                    if hasattr(p, 'Amount') and p.Amount > 0:
                        mounted_products.append(p)
        
        # Get unique items
        items = []
        seen_items = set()
        for mp in mounted_products:
            item = getattr(mp, 'Item', None)
            if item is not None:
                item_id = id(item)
                if item_id not in seen_items:
                    seen_items.add(item_id)
                    items.append(item)
        
        # Collect all delivery order safe side entries
        delivery_safe_sides = []
        for item in items:
            if hasattr(item, 'DeliveryOrderSafeSide'):
                dos = item.DeliveryOrderSafeSide
                if dos:
                    # DeliveryOrderSafeSide can be dict or list of tuples
                    if isinstance(dos, dict):
                        for delivery_order, safe_side in dos.items():
                            delivery_safe_sides.append((delivery_order, safe_side))
                    else:
                        # Assume iterable of tuples/pairs
                        for entry in dos:
                            if isinstance(entry, tuple) and len(entry) >= 2:
                                delivery_safe_sides.append((entry[0], entry[1]))
        
        return delivery_safe_sides
    
    def GetDeliveriesHelperSafeSide(self) -> List[int]:
        """
        C#: GetDeliveriesHelperSafeSide - Returns delivery orders on Helper safe side.
        
        Returns:
            List of unique delivery order IDs where safe side == Helper (2)
        """
        from .truck_safe_side import TruckSafeSide
        deliveries = self.GetDeliveriesSafeSide()
        helper_deliveries = [d for d, side in deliveries if side == int(TruckSafeSide.HELPER)]
        return list(set(helper_deliveries))  # Distinct
    
    def GetDeliveriesDriverSafeSide(self) -> List[int]:
        """
        C#: GetDeliveriesDriverSafeSide - Returns delivery orders on Driver safe side.
        
        Returns:
            List of unique delivery order IDs where safe side == Driver (3)
        """
        from .truck_safe_side import TruckSafeSide
        deliveries = self.GetDeliveriesSafeSide()
        driver_deliveries = [d for d, side in deliveries if side == int(TruckSafeSide.DRIVER)]
        return list(set(driver_deliveries))  # Distinct
    
    def GetDeliveriesIndifferentSafeSide(self) -> List[int]:
        """
        C#: GetDeliveriesIndifferentSafeSide - Returns delivery orders with Indifferent safe side.
        
        Returns:
            List of unique delivery order IDs where safe side == Indifferent (1)
        """
        from .truck_safe_side import TruckSafeSide
        deliveries = self.GetDeliveriesSafeSide()
        indifferent_deliveries = [d for d, side in deliveries if side == int(TruckSafeSide.INDIFFERENT)]
        return list(set(indifferent_deliveries))  # Distinct
    
    def GetNotChoppNotBalancedSpaces(self) -> List["Space"]:
        """
        C#: GetNotChoppNotBalancedSpaces - Returns spaces that are not chopp and not balanced.
        
        Extension method from RuleContextExtensions.cs:
        var emptySpaces = context.Spaces.ToList();
        var notChoppSpaces = context.MountedSpaces.NotChopp().Select(x => x.Space).ToList();
        return emptySpaces.Concat(notChoppSpaces).Distinct().NotBalanced();
        
        Returns:
            List of spaces (empty + not chopp mounted spaces) that are not balanced
        """
        from .mounted_space_list import MountedSpaceList
        
        # Empty spaces
        empty_spaces = list(self.Spaces)
        
        # Not chopp mounted spaces
        not_chopp_spaces = []
        not_chopp_mounted = MountedSpaceList(self._mounted_spaces).NotChopp()
        for ms in not_chopp_mounted:
            not_chopp_spaces.append(ms.Space)
        
        # Combine and remove duplicates
        all_spaces = empty_spaces + not_chopp_spaces
        unique_spaces = list({id(s): s for s in all_spaces}.values())
        
        # Filter not balanced (NotBalanced extension)
        not_balanced_spaces = []
        for space in unique_spaces:
            # Check if space is balanced (has Balanced property set to True)
            is_balanced = False
            if hasattr(space, 'Balanced'):
                is_balanced = getattr(space, 'Balanced', False)
            
            if not is_balanced:
                not_balanced_spaces.append(space)
        
        return not_balanced_spaces
    
    def GetMountedSpacesBalanced(self) -> List["MountedSpace"]:
        """
        C#: GetMountedSpacesBalanced - Returns mounted spaces that are balanced.
        
        Extension method from RuleContextExtensions.cs:
        context.MountedSpaces.Where(x => x.Space is ITruckBayRoute truckBayRoute && truckBayRoute.Balanced)
        
        Returns:
            List of mounted spaces where space is balanced
        """
        balanced_mounted_spaces = []
        for ms in self._mounted_spaces:
            space = getattr(ms, 'Space', None)
            if space is not None:
                # Check if space is balanced (TruckBayRoute.Balanced property)
                is_balanced = getattr(space, 'Balanced', False)
                if is_balanced:
                    balanced_mounted_spaces.append(ms)
        return balanced_mounted_spaces
    
    def HasNotChoppNotBalancedSpaces(self) -> bool:
        """
        C#: HasNotChoppNotBalancedSpaces - Checks if there are not chopp not balanced spaces.
        
        Extension method from RuleContextExtensions.cs:
        context.GetNotChoppNotBalancedSpaces().Any()
        
        Returns:
            True if there are not chopp not balanced spaces, False otherwise
        """
        return len(self.GetNotChoppNotBalancedSpaces()) > 0
    
    def GetComplexLoadCustomer(self) -> int:
        """
        C#: GetComplexLoadCustomer - Returns the customer ID of the complex load.
        
        Extension method from RuleContextExtensions.cs:
        context.MountedSpaces
            .SelectMany(x => x.GetProducts().Where(x => x.ComplexLoad))
            .Select(x => x.Customer)
            .FirstOrDefault()
        
        Returns:
            Customer ID of the first complex load product, or 0 if not found
        """
        # iterate through mounted spaces using the public property so any mounted-space
        # filter applied by RouteRuleContext.WithMountedSpaceFilter is respected.
        for ms in list(self.MountedSpaces) if hasattr(self, 'MountedSpaces') else list(self._mounted_spaces):
            try:
                if hasattr(ms, 'GetProducts'):
                    products = ms.GetProducts()
                    for p in products:
                        is_complex_load = getattr(p, 'ComplexLoad', False)
                        if is_complex_load:
                            customer = getattr(p, 'Customer', 0)
                            return customer
            except Exception:
                continue
        return 0
    
    def GetComplexDeliveryOrder(self) -> int:
        """
        C#: GetComplexDeliveryOrder - Returns the delivery order of the complex load.
        
        Extension method from RuleContextExtensions.cs:
        var complexLoadCustomer = GetComplexLoadCustomer(context);
        return context.MountedSpaces
            .SelectMany(x => x.GetProducts().Where(x => x.ComplexLoad))
            .Select(x => x.Item.GetClientDeliveryOrder(complexLoadCustomer))
            .FirstOrDefault();
        
        Returns:
            Delivery order ID of the complex load, or 0 if not found
        """
        complex_load_customer = self.GetComplexLoadCustomer()

        # iterate via public MountedSpaces to respect any mounted-space filters
        for ms in list(self.MountedSpaces) if hasattr(self, 'MountedSpaces') else list(self._mounted_spaces):
            try:
                if hasattr(ms, 'GetProducts'):
                    products = ms.GetProducts()
                    for p in products:
                        is_complex_load = getattr(p, 'ComplexLoad', False)
                        if is_complex_load:
                            item = getattr(p, 'Item', None)
                            if item is not None and hasattr(item, 'GetClientDeliveryOrder'):
                                delivery_order = item.GetClientDeliveryOrder(complex_load_customer)
                                return delivery_order
            except Exception:
                continue
        return 0
    
    def IsKegExclusivePallet(self) -> bool:
        return self.Settings.get('KegExclusivePallet', False)
    
    def CanBeAssociate(self, mounted_space: Optional["MountedSpace"], item: "Item") -> bool:
        """
        C#: CanBeAssociate - Checks if item can be associated with mounted space.
        
        Extension method from RuleContextExtensions.cs:
        - If mounted_space is null, return true
        - If ShouldLimitPackageGroups is false, return true
        - Check if item's PackingGroup can be associated with existing groups
        
        Args:
            mounted_space: MountedSpace to check association
            item: Item to check if can be associated
            
        Returns:
            True if item can be associated, False otherwise
        """
        if mounted_space is None:
            return True
        
        limit_groups = self.Settings.get('ShouldLimitPackageGroups', False)
        if not limit_groups:
            return True
        
        # Get current groups in mounted space
        current_groups = []
        containers = getattr(mounted_space, 'Containers', [])
        for container in containers:
            products = getattr(container, 'Products', [])
            for product in products:
                prod = getattr(product, 'Product', None)
                if prod is not None:
                    packing_group = getattr(prod, 'PackingGroup', None)
                    if packing_group is not None:
                        group_code = getattr(packing_group, 'GroupCode', None)
                        if group_code is not None and group_code not in current_groups:
                            current_groups.append(group_code)
        
        # Get item's group code
        item_prod = getattr(item, 'Product', None)
        if item_prod is None:
            return True
        
        item_packing_group = getattr(item_prod, 'PackingGroup', None)
        if item_packing_group is None:
            return True
        
        item_group_code = getattr(item_packing_group, 'GroupCode', None)
        
        # If item's group is already in mounted space, allow
        if item_group_code in current_groups:
            return True
        
        # Check if item can be associated with all existing groups
        for group_code in current_groups:
            if not item_prod.CanBeAssociated(group_code):
                return False
        
        return True

    def GetNotFullSpaces(self, mounted_spaces: Optional[List["MountedSpace"]] = None) -> List["Space"]:
        """
        C#: GetNotFullSpaces - Returns spaces that are either empty or not full and not blocked.
        
        Returns:
            List of spaces (empty spaces + spaces from mounted spaces that have room and are not blocked)
        """
        if mounted_spaces is None:
            mounted_spaces = self._mounted_spaces
        
        # Empty spaces are always available
        empty_spaces = list(self.Spaces)
        
        # Get spaces from mounted spaces that still have room and are not blocked
        not_full_spaces = []
        for ms in mounted_spaces:
            # Check if has space and not blocked (HasSpaceAndNotBlocked)
            has_space = getattr(ms, 'HasSpace', lambda: True)()
            is_blocked = getattr(ms, 'IsBlocked', lambda: False)()
            
            if has_space and not is_blocked:
                not_full_spaces.append(ms.Space)
        
        # Combine and remove duplicates
        all_spaces = empty_spaces + not_full_spaces
        # Use dict to maintain order and remove duplicates
        return list({id(s): s for s in all_spaces}.values())
    
    def GetEmptySpaces(self) -> List["Space"]:
        """
        C#: GetEmptySpaces - Returns spaces that are completely empty.
        
        Returns:
            List of empty spaces (unmounted spaces + mounted spaces that are empty and not blocked)
        """
        # Unmounted spaces (available spaces)
        empty_spaces = list(self.Spaces)
        
        # Get mounted spaces that are empty and not blocked
        empty_mounted_spaces = []
        for ms in self._mounted_spaces:
            # Check if has space and not blocked
            has_space = getattr(ms, 'HasSpace', lambda: True)()
            is_blocked = getattr(ms, 'IsBlocked', lambda: False)()
            is_empty = getattr(ms, 'IsEmpty', lambda: True)()
            
            if has_space and not is_blocked and is_empty:
                empty_mounted_spaces.append(ms.Space)
        
        # Combine and remove duplicates
        all_empty = empty_spaces + empty_mounted_spaces
        # Use dict to maintain order and remove duplicates
        return list({id(s): s for s in all_empty}.values())

    # snake_case aliases for remaining Context methods
    def get_items(self) -> List["Item"]:
        return self.GetItems()

    def get_items_palletizable_by_order(self, order: "Order") -> List["Item"]:
        return self.GetItemsPalletizableByOrder(order)

    def get_items_with_amount_remaining(self) -> List["Item"]:
        return self.GetItemsWithAmountRemaining()

    def get_items_with_detached_amount(self) -> List["Item"]:
        return self.GetItemsWithDetachedAmount()

    def add_mounted_space_from_space(self, space: "Space", order: Optional["Order"] = None) -> "MountedSpace":
        return self.AddMountedSpaceFromSpace(space, order)

    def remove_mounted_space(self, mounted_space: "MountedSpace"):
        return self.RemoveMountedSpace(mounted_space)

    def get_mounted_space_by_id(self, id_value: Any) -> Optional["MountedSpace"]:
        return self.GetMountedSpaceById(id_value)
    
    def GetMountedSpace(self, space: "Space") -> Optional["MountedSpace"]:
        """
        C#: GetMountedSpace - Returns the mounted space for the given space.
        
        Extension method from RuleContextExtensions.cs:
        context.MountedSpaces.FirstOrDefault(x => x.Space.Equals(space))
        
        Args:
            space: Space to search for
            
        Returns:
            MountedSpace that contains the given space, or None if not found
        """
        for ms in self._mounted_spaces:
            ms_space = getattr(ms, 'Space', None)
            if ms_space is not None:
                # Use Equals if available, otherwise compare by reference or Number+Side
                if hasattr(ms_space, 'Equals'):
                    if ms_space.Equals(space):
                        return ms
                elif ms_space == space:
                    return ms
                else:
                    # Fallback: compare by Number and Side
                    ms_number = getattr(ms_space, 'Number', None)
                    ms_side = getattr(ms_space, 'Side', None)
                    space_number = getattr(space, 'Number', None)
                    space_side = getattr(space, 'Side', None)
                    
                    if ms_number == space_number and ms_side == space_side:
                        return ms
        return None
    
    def get_mounted_space(self, space: "Space") -> Optional["MountedSpace"]:
        """snake_case alias for GetMountedSpace"""
        return self.GetMountedSpace(space)

    def GetMountedSpaceTemporary(self, space: "Space", order: Optional["Order"] = None) -> "MountedSpace":
        """
        Return a mounted-space for `space` without persisting it in the context.

        Behavior:
          - If an existing mounted-space for `space` exists in the context, return it.
          - Otherwise construct a new `MountedSpace(space=space, order=order)` and return
            it WITHOUT appending it to `self._mounted_spaces` (transient only).
        This is useful for rules that need a mounted-space-shaped object for calculations
        but shouldn't mutate the context state.
        """
        # Try to return existing mounted-space if present
        existing = self.GetMountedSpace(space)
        if existing is not None:
            return existing

        # Create a transient MountedSpace instance but do NOT add it to context
        try:
            temp_ms = MountedSpace(space=space, order=order)
        except Exception:
            temp_ms = MountedSpace()
            try:
                setattr(temp_ms, 'Space', space)
            except Exception:
                pass
            try:
                setattr(temp_ms, 'Order', order)
            except Exception:
                pass

        # Ensure it has an identifier-like attribute for compatibility
        if not getattr(temp_ms, 'MountedSpaceId', None) and not getattr(temp_ms, 'Id', None):
            try:
                temp_ms.MountedSpaceId = id(temp_ms)
            except Exception:
                try:
                    setattr(temp_ms, 'MountedSpaceId', id(temp_ms))
                except Exception:
                    pass

        return temp_ms

    def get_mounted_space_temporary(self, space: "Space", order: Optional["Order"] = None) -> "MountedSpace":
        """snake_case alias for GetMountedSpaceTemporary"""
        return self.GetMountedSpaceTemporary(space, order)

    def get_spaces_dto(self) -> List[dict]:
        return self.GetSpacesDto()
    
    def get_not_full_spaces(self, mounted_spaces: Optional[List["MountedSpace"]] = None) -> List["Space"]:
        return self.GetNotFullSpaces(mounted_spaces)
    
    def get_empty_spaces(self) -> List["Space"]:
        return self.GetEmptySpaces()

    def add_product(self, space: "Space", item: "Item", quantity: int, occupation: Optional[Decimal] = None) -> "MountedSpace":
        return self.AddProduct(space, item, quantity, occupation)
    
    def add_complex_load_product(self, space: "Space", item: "Item", quantity: int, occupation: Decimal, customer: int) -> "MountedSpace":
        return self.AddComplexLoadProduct(space, item, quantity, occupation, customer)

    # --- Status / flow control ------------------------------------------
    def SetStatus(self, status: str):
        self.Status = status

    # --- Switch / move mounted-products helpers --------------------------
    def SwitchProducts(self, target_mounted_space: "MountedSpace", source_mounted_space: "MountedSpace", total_occupation: Optional[Decimal] = None):
        """
        Move all products from source to target, update occupations and weights.
        Mirrors C# RuleContext.SwitchProducts semantics:
          - Get all products from source containers
          - Add each product to target.Containers[0]
          - Set target occupation
          - Clear source
        
        C# code:
            var productsToAdd = mountedSpaceToRemove.Containers.SelectMany(x => x.Products);
            foreach (var products in productsToAdd)
                mountedSpaceToAdd.Containers[0].AddMountedProduct(products);
            
            mountedSpaceToAdd.SetOccupation(occupation);
            mountedSpaceToRemove.Clear();
        """
        # C#: mountedSpaceToRemove.Containers.SelectMany(x => x.Products)
        products_to_add = []
        for container in source_mounted_space.Containers:
            products_to_add.extend(container.Products or [])
        
        # C#: foreach (var products in productsToAdd) mountedSpaceToAdd.Containers[0].AddMountedProduct(products);
        if target_mounted_space.Containers:
            target_container = target_mounted_space.Containers[0]
            for p in products_to_add:
                # Add to target container
                if hasattr(target_container, 'AddMountedProduct'):
                    target_container.AddMountedProduct(p)
                elif hasattr(target_container, 'Products'):
                    target_container.Products.append(p)
                
                # Update product's MountedSpace reference
                try:
                    p.MountedSpace = target_mounted_space
                except Exception:
                    pass
        
        # C#: mountedSpaceToAdd.SetOccupation(occupation);
        if total_occupation is not None:
            target_mounted_space.SetOccupation(total_occupation)
        
        # C#: mountedSpaceToRemove.Clear();
        source_mounted_space.Clear()

    # snake_case alias
    def switch_products(self, target_mounted_space: "MountedSpace", source_mounted_space: "MountedSpace", total_occupation: Optional[Decimal] = None):
        return self.SwitchProducts(target_mounted_space, source_mounted_space, total_occupation)

    def _get_percentage_weight_of_side(self) -> str:
        # Backwards-compatible helper: returns a formatted string with weights and percentages
        try:
            summary = self.GetSideWeightSummary()
            m = summary.get('motorista', {})
            a = summary.get('ajudante', {})
            return f"Lado Motorista: {m.get('weight', 0.0):.2f} ({m.get('pct', 0.0):.2f}%) - Lado Ajudante: {a.get('weight', 0.0):.2f} ({a.get('pct', 0.0):.2f}%)"
        except Exception:
            return "Lado Motorista: 0.00 (0.00%) - Lado Ajudante: 0.00 (0.00%)"

    # --- convenience item lookup (used by some rules) --------------------
    def GetAllItems(self) -> List["Item"]:
        """
        C#: GetAllItems - Returns all items from all orders.
        
        Extension method from RuleContextExtensions.cs:
        context.Orders.SelectMany(x => x.Items)
        
        Returns:
            List of all items from all orders
        """
        items = []
        for o in self.Orders:
            try:
                items.extend(o.Items)
            except Exception:
                try:
                    items.extend(getattr(o, "GetItems", lambda: [])())
                except Exception:
                    pass
        return items

    def GetSideWeightSummary(self) -> dict:
        """Return weight and percentage summary for driver (motorista) and helper (ajudante).

        Returns a dict: {
            'motorista': {'weight': float, 'pct': float},
            'ajudante': {'weight': float, 'pct': float},
            'total': float
        }
        Percentages are in [0,100]. We compute weights using mounted_spaces Weight/weight property.
        """
        mspaces = list(getattr(self, 'mounted_spaces', []) or [])
        total_weight = 0.0
        try:
            total_weight = sum(float(getattr(ms, 'Weight', getattr(ms, 'weight', 0.0)) or 0.0) for ms in mspaces)
        except Exception:
            total_weight = 0.0

        try:
            driver_list = list(MountedSpaceList(mspaces).DriverSide())
        except Exception:
            # fallback: consider spaces with Side starting with 'M' as driver
            driver_list = [ms for ms in mspaces if str(getattr(getattr(ms, 'Space', getattr(ms, 'space', None)), 'Side', getattr(ms, 'Side', getattr(ms, 'side', '')))).upper().startswith('M')]

        driver_weight = 0.0
        try:
            driver_weight = sum(float(getattr(ms, 'Weight', getattr(ms, 'weight', 0.0)) or 0.0) for ms in driver_list)
        except Exception:
            driver_weight = 0.0

        ajudante_weight = max(0.0, (total_weight - driver_weight))

        driver_pct = (driver_weight * 100.0 / total_weight) if total_weight else 0.0
        ajudante_pct = (ajudante_weight * 100.0 / total_weight) if total_weight else 0.0

        return {
            'motorista': {'weight': driver_weight, 'pct': driver_pct},
            'ajudante': {'weight': ajudante_weight, 'pct': ajudante_pct},
            'total': total_weight,
        }

    # snake_case alias
    def get_side_weight_summary(self) -> dict:
        return self.GetSideWeightSummary()
    
    def GetAllProducts(self):
        """Return list of all MountedProduct instances present in mounted_spaces/containers."""
        prods = []
        try:
            for ms in getattr(self, "mounted_spaces", []) or []:
                containers = getattr(ms, "containers", getattr(ms, "Containers", [])) or []
                for c in containers:
                    try:
                        # prefer container.get_products() if exists
                        if hasattr(c, "get_products"):
                            prods.extend(list(c.get_products() or []))
                        else:
                            prods.extend(getattr(c, "products", getattr(c, "Products", [])) or [])
                    except Exception:
                        continue
        except Exception:
            pass
        return prods
    
    def GetItems(self) -> List["Item"]:
        """
        C#: GetItems - Returns items that can be palletized.
        
        Extension method from RuleContextExtensions.cs:
        context.GetAllItems().Where(x => x.Product.CanBePalletized)
        
        Returns:
            List of items that can be palletized (Product.CanBePalletized == true)
        """
        all_items = self.GetAllItems()
        palletizable_items = []
        for item in all_items:
            prod = getattr(item, "Product", getattr(item, "product", None))
            if prod is not None:
                can_be_palletized = getattr(prod, "CanBePalletized", getattr(prod, "can_be_palletized", False))
                if can_be_palletized:
                    palletizable_items.append(item)
        return palletizable_items

    # --- Additional helpers ported from C# RuleContext ------------------
    def GetItemsPalletizableByOrder(self, order: "Order") -> List["Item"]:
        """Return items of `order` that can be palletized and have amount remaining.

        Matches typical C# helper semantics used by rules.
        """
        items = []
        try:
            items = list(order.Items)
        except Exception:
            try:
                items = list(getattr(order, "GetItems", lambda: [])())
            except Exception:
                items = []

        def can_palletize(i: Any) -> bool:
            prod = getattr(i, "Product", getattr(i, "product", None))
            can = False
            try:
                can = bool(getattr(prod, "CanBePalletized", getattr(prod, "can_be_palletized", False)))
            except Exception:
                can = False
            amount_rem = getattr(i, "AmountRemaining", getattr(i, "amount_remaining", getattr(i, "Amount", getattr(i, "amount", 0))))
            return can and (amount_rem > 0)

        return [i for i in items if can_palletize(i)]

    def GetItemsWithAmountRemaining(self) -> List["Item"]:
        """Return all items across orders with amount remaining > 0."""
        return [i for i in self.GetItems() if getattr(i, "AmountRemaining", getattr(i, "amount_remaining", getattr(i, "Amount", 0))) > 0]

    def GetItemsWithDetachedAmount(self) -> List["Item"]:
        """Return all items that have detached amount > 0 (used by DetachedUnitRule)."""
        return [i for i in self.GetItems() if getattr(i, "DetachedAmount", getattr(i, "detached_amount", 0)) > 0]
    
    # --- snake_case aliases for RuleContextExtensions methods ---
    def get_all_items(self) -> List["Item"]:
        """snake_case alias for GetAllItems"""
        return self.GetAllItems()
    
    def get_items(self) -> List["Item"]:
        """snake_case alias for GetItems"""
        return self.GetItems()
    
    def get_all_products(self) -> List["Item"]:
        """snake_case alias for GetAllProducts"""
        return self.GetAllProducts()
    
    def get_not_chopp_not_balanced_spaces(self) -> List["Space"]:
        """snake_case alias for GetNotChoppNotBalancedSpaces"""
        return self.GetNotChoppNotBalancedSpaces()
    
    def get_mounted_spaces_balanced(self) -> List["MountedSpace"]:
        """snake_case alias for GetMountedSpacesBalanced"""
        return self.GetMountedSpacesBalanced()
    
    def has_not_chopp_not_balanced_spaces(self) -> bool:
        """snake_case alias for HasNotChoppNotBalancedSpaces"""
        return self.HasNotChoppNotBalancedSpaces()
    
    def get_complex_load_customer(self) -> int:
        """snake_case alias for GetComplexLoadCustomer"""
        return self.GetComplexLoadCustomer()
    
    def get_complex_delivery_order(self) -> int:
        """snake_case alias for GetComplexDeliveryOrder"""
        return self.GetComplexDeliveryOrder()
    
    def is_keg_exclusive_pallet(self) -> bool:
        """snake_case alias for IsKegExclusivePallet"""
        return self.IsKegExclusivePallet()
    
    def can_be_associate(self, mounted_space: Optional["MountedSpace"], item: "Item") -> bool:
        """snake_case alias for CanBeAssociate"""
        return self.CanBeAssociate(mounted_space, item)

    def AddMountedSpaceFromSpace(self, space: "Space", order: Optional["Order"] = None) -> "MountedSpace":
        """Create a new MountedSpace based on Space and append to MountedSpaces.

        The created object tries to use the project's MountedSpace class if available; otherwise
        a lightweight proxy object is returned. This mirrors C# RuleContext.AddMountedSpaceFromSpace.
        """
        try:
            ms = MountedSpace(space=space, order=order)
        except Exception:
            # fallback constructor signature
            ms = MountedSpace()
            setattr(ms, "Space", space)
            setattr(ms, "Order", order)

        # give it an Id if not present
        if not getattr(ms, "MountedSpaceId", None) and not getattr(ms, "Id", None):
            try:
                ms.MountedSpaceId = id(ms)
            except Exception:
                setattr(ms, "MountedSpaceId", id(ms))

        # Use AddMountedSpace to mimic C# semantics (remove underlying Space from available spaces)
        try:
            self.AddMountedSpace(ms)
        except Exception:
            # best-effort fallback
            self.MountedSpaces.append(ms)

        return ms

    def AddMountedSpace(self, mounted_space: "MountedSpace"):
        """Add an existing MountedSpace to the context.

        Mirrors C# RuleContext.AddMountedSpace which removes the underlying
        Space from the available spaces list and appends the mounted space.
        """
        # try to remove the referenced Space from _spaces
        try:
            sp = getattr(mounted_space, 'Space', None)
            if sp is not None:
                try:
                    # direct removal if same object
                    self._spaces.remove(sp)
                except Exception:
                    # fallback: try to match by Number and Side
                    sp_num = getattr(sp, 'Number', None)
                    sp_side = getattr(sp, 'Side', None)
                    for s in list(self._spaces):
                        if getattr(s, 'Number', None) == sp_num and getattr(s, 'Side', None) == sp_side:
                            try:
                                self._spaces.remove(s)
                            except Exception:
                                pass
                            break
        except Exception:
            pass

        # append to mounted spaces
        try:
            self._mounted_spaces.append(mounted_space)
        except Exception:
            try:
                self.MountedSpaces.append(mounted_space)
            except Exception:
                # as last resort, set attribute
                if not hasattr(self, '_mounted_spaces'):
                    setattr(self, '_mounted_spaces', [])
                self._mounted_spaces.append(mounted_space)

    def RemoveMountedSpace(self, mounted_space: "MountedSpace"):
        try:
            self.MountedSpaces.remove(mounted_space)
        except ValueError:
            # try identity-based removal
            for m in list(self.MountedSpaces):
                if m is mounted_space:
                    self.MountedSpaces.remove(m)
                    break

    def GetMountedSpaceById(self, id_value: Any) -> Optional["MountedSpace"]:
        for m in self._mounted_spaces:
            if getattr(m, "MountedSpaceId", getattr(m, "Id", None)) == id_value:
                return m
        return None

    def GetSpacesDto(self) -> List[dict]:
        """Build a simple DTO list combining Spaces and MountedSpace ids.

        Structure: list of {'Space': space, 'MountedSpace': mounted_space, 'MountedSpaceId': id}
        This is compatible with many C# rules that iterate space-mounted mappings.
        """
        dtos = []
        mounted_map = {getattr(m, "MountedSpaceId", getattr(m, "Id", None)): m for m in self._mounted_spaces}
        for s in self.Spaces:
            # find mounted entries that reference this space
            for mid, m in mounted_map.items():
                if getattr(m, "Space", None) == s:
                    dtos.append({"Space": s, "MountedSpace": m, "MountedSpaceId": mid})
        # include mounted spaces without explicit space mapping
        for m in self._mounted_spaces:
            mid = getattr(m, "MountedSpaceId", getattr(m, "Id", None))
            if not any(d.get("MountedSpace") is m for d in dtos):
                dtos.append({"Space": getattr(m, "Space", None), "MountedSpace": m, "MountedSpaceId": mid})
        return dtos

    def AddProduct(self, *args, **kwargs) -> "MountedSpace":
        """Flexible AddProduct compatible with C# overloads.

        Supports calls:
          - AddProduct(space, item, quantity)
          - AddProduct(space, item, quantity, occupation)
          - AddProduct(space, item, quantity, firstLayer, quantityOfLayer, occupation)
          - AddProduct(mountedSpace, item, quantity, firstLayer, quantityOfLayer, occupation)

        This normalizes arguments and delegates to the existing helpers that
        create MountedProduct and insert into a MountedSpace.
        """
        from .container import Container
        from .mounted_product import MountedProduct

        if len(args) < 3:
            raise TypeError("AddProduct requires at least (space_or_mounted, item, quantity)")

        space_or_mounted = args[0]
        item = args[1]
        quantity = int(args[2])

        # defaults
        first_layer = 0
        quantity_of_layer = 0
        occupation = None

        # parse remaining positional args
        if len(args) == 4:
            occupation = args[3]
        elif len(args) >= 6:
            first_layer = int(args[3])
            quantity_of_layer = int(args[4])
            occupation = args[5]

        # detect if first arg is a MountedSpace
        mounted_space_arg = None
        space = None
        if hasattr(space_or_mounted, 'GetProducts') or hasattr(space_or_mounted, 'Containers'):
            mounted_space_arg = space_or_mounted
            space = getattr(mounted_space_arg, 'Space', None)
        else:
            space = space_or_mounted

        # if quantity_of_layer not provided, compute from PalletSetting.QuantityBallast when possible
        try:
            if quantity_of_layer == 0 and hasattr(item, 'Product') and item.Product is not None:
                ps = getattr(item.Product, 'PalletSetting', None)
                if ps is not None and getattr(ps, 'QuantityBallast', None):
                    quantity_of_layer = int(quantity / int(ps.QuantityBallast))
        except Exception:
            quantity_of_layer = quantity_of_layer or 0

        # calculate occupation if not provided
        if occupation is None:
            try:
                occupation = Decimal(getattr(space, 'Size', getattr(space, 'size', 0)))
            except Exception:
                occupation = Decimal(0)

        # find order
        order = None
        for o in self.Orders:
            if hasattr(o, 'Items') and item in o.Items:
                order = o
                break

        # create MountedProduct
        product_occupation = Decimal(occupation) - getattr(item, 'AdditionalOccupation', Decimal(0))
        mounted_product = MountedProduct(
            item=item,
            product=item.Product if hasattr(item, 'Product') else None,
            order=order,
            quantity_of_layers=quantity_of_layer,
            first_layer_index=first_layer,
            occupation=product_occupation,
        )

        # #temporario novo
        # cust = getattr(item, '_customer', None) or getattr(item, 'Customer', None) or getattr(order, 'Customer', None) or getattr(order, 'customer', None)
        # if cust not in (None, '', 0):
        #     mounted_product.SetCustomer(cust)
                
        # set additional occupation
        if getattr(item, 'AdditionalOccupation', 0) > 0:
            if hasattr(mounted_product, 'SetAdditionalOccupation'):
                mounted_product.SetAdditionalOccupation(item.AdditionalOccupation)
            else:
                mounted_product.AdditionalOccupation = item.AdditionalOccupation

        # delegate to helper that inserts into mounted space (creates if needed)
        mounted_space = self._add_mounted_product_to_mounted_space(space, order, quantity, mounted_product, 0)

        # update occupation on mounted_space
        if hasattr(mounted_space, 'IncreaseOccupation'):
            mounted_space.IncreaseOccupation(Decimal(occupation))
        else:
            mounted_space.Occupation = Decimal(getattr(mounted_space, 'Occupation', Decimal(0))) + Decimal(occupation)

        # subtract item amount
        if hasattr(item, 'SubtractAmount'):
            item.SubtractAmount(quantity)
        else:
            item.AmountRemaining = max(0, getattr(item, 'AmountRemaining', 0) - quantity)

        # set ballast on first pallet if PalletSetting indicates
        try:
            ballast = 0
            ps = getattr(item.Product, 'PalletSetting', None)
            if ps is not None and getattr(ps, 'Layers', None):
                import math
                layers = int(getattr(ps, 'Layers') or 1)
                ballast = int(math.ceil(quantity / Decimal(layers)))
            if ballast > 0:
                first_pallet = mounted_space.GetFirstPallet() if hasattr(mounted_space, 'GetFirstPallet') else (mounted_space.Containers[0] if getattr(mounted_space, 'Containers', None) else None)
                if first_pallet is not None and hasattr(first_pallet, 'SetBallast'):
                    first_pallet.SetBallast(ballast)
        except Exception:
            pass

        return mounted_space

    def AddProductFromMountedProduct(self, space: "Space", source_mounted_product: "MountedProduct", quantity: int, first_layer: int, quantity_of_layer: int, occupation) -> "MountedSpace":
        """Port of C# RuleContext.AddProductFromMountedProduct.

        Creates a clone of `source_mounted_product` with the requested quantity
        and inserts it into a mounted space for `space`. Does not remove
        occupation from the source mounted-space (caller handles that).
        """
        # try to find the order associated with the source product
        order = getattr(source_mounted_product, 'Order', None)

        # clone the mounted product and set requested quantity/layers/occupation
        try:
            cloned = source_mounted_product.Clone(self.Orders) if hasattr(source_mounted_product, 'Clone') else deepcopy(source_mounted_product)
        except Exception:
            try:
                cloned = source_mounted_product.clone(self.Orders)
            except Exception:
                # fallback shallow copy
                cloned = deepcopy(source_mounted_product)

        try:
            cloned.Amount = int(quantity)
        except Exception:
            try:
                setattr(cloned, 'Amount', int(quantity))
            except Exception:
                pass

        try:
            cloned.FirstLayerIndex = int(first_layer)
        except Exception:
            try:
                setattr(cloned, 'FirstLayerIndex', int(first_layer))
            except Exception:
                pass

        try:
            cloned.QuantityOfLayers = int(quantity_of_layer)
        except Exception:
            try:
                setattr(cloned, 'QuantityOfLayers', int(quantity_of_layer))
            except Exception:
                pass

        try:
            if hasattr(cloned, 'SetOccupation'):
                cloned.SetOccupation(occupation)
            else:
                cloned.occupation = occupation
        except Exception:
            pass

        # mark as splitted when quantity differs from original
        try:
            original_amount = getattr(source_mounted_product, 'Amount', getattr(source_mounted_product, 'amount', None))
            if original_amount is not None and int(quantity) < int(original_amount):
                if hasattr(source_mounted_product, 'Split'):
                    try:
                        source_mounted_product.Split()
                    except Exception:
                        setattr(source_mounted_product, 'Splitted', True)
                else:
                    try:
                        source_mounted_product.Splitted = True
                    except Exception:
                        pass
        except Exception:
            pass

        # insert into destination mounted space
        try:
            dest_ms = self._add_mounted_product_to_mounted_space(space, order, quantity, cloned, 0)
        except Exception:
            # best-effort fallback: call AddProduct using Item if present
            item = getattr(source_mounted_product, 'Item', getattr(source_mounted_product, 'item', None))
            try:
                dest_ms = self.AddProduct(space, item, quantity, first_layer, quantity_of_layer, occupation)
            except Exception:
                dest_ms = None

        # increase occupation on destination mounted space
        try:
            if dest_ms is not None:
                if hasattr(dest_ms, 'IncreaseOccupation'):
                    dest_ms.IncreaseOccupation(occupation)
                elif hasattr(dest_ms, 'SetOccupation'):
                    # sum with existing
                    cur = getattr(dest_ms, 'Occupation', getattr(dest_ms, 'occupation', 0))
                    try:
                        dest_ms.SetOccupation(Decimal(cur) + Decimal(occupation))
                    except Exception:
                        dest_ms.Occupation = getattr(dest_ms, 'Occupation', 0) + occupation
                else:
                    try:
                        cur = getattr(dest_ms, 'occupation', 0) or 0
                        dest_ms.occupation = cur + occupation
                    except Exception:
                        pass
        except Exception:
            pass

        # subtract amount from source mounted product (caller will adjust occupations)
        try:
            if hasattr(source_mounted_product, 'SubtractAmount'):
                source_mounted_product.SubtractAmount(quantity)
            else:
                source_mounted_product.Amount = max(0, getattr(source_mounted_product, 'Amount', getattr(source_mounted_product, 'amount', 0)) - int(quantity))
        except Exception:
            pass

        return dest_ms

    def add_product_from_mounted_product(self, *args, **kwargs):
        return self.AddProductFromMountedProduct(*args, **kwargs)

    def AddComplexLoadProduct(self, space: "Space", item: "Item", quantity: int, occupation: Decimal, customer: int) -> "MountedSpace":
        """
        C#: AddComplexLoadProduct - Add complex load product (with customer) to mounted space.
        
        Mirrors C# RuleContext.AddComplexLoadProduct logic:
        1. Calculate ballast and layer info
        2. Create MountedProduct with customer
        3. Add to MountedSpace
        4. Update occupation and subtract item amount
        5. Subtract customer quantity
        
        Args:
            space: Space where product will be added
            item: Item to add
            quantity: Quantity to add
            occupation: Occupation value
            customer: Customer ID for complex load
            
        Returns:
            MountedSpace where product was added
        """
        from .container import Container
        from .mounted_product import MountedProduct
        import math
        
        # Calculate ballast and quantityOfLayer
        layers = 1
        if hasattr(item, 'Product') and item.Product is not None:
            pallet_setting = getattr(item.Product, 'PalletSetting', None)
            if pallet_setting is not None:
                layers = getattr(pallet_setting, 'Layers', 1) or 1
        
        ballast = int(math.ceil(quantity / Decimal(layers)))
        quantity_of_layer = quantity // ballast if ballast > 0 else quantity
        
        # Get the order that contains this item
        order = None
        for o in self._orders:
            if hasattr(o, 'Items') and item in o.Items:
                order = o
                break
        
        # Create MountedProduct with customer
        mounted_product = MountedProduct(
            item=item,
            product=item.Product if hasattr(item, 'Product') else None,
            order=order,
            quantity_of_layers=quantity_of_layer,
            first_layer_index=0,
            occupation=occupation,
            customer=customer
        )
        
        mounted_product.Customer = customer
        mounted_product.ComplexLoad = (customer != 0)
    
        # Calculate real occupation (including additional)
        real_occupation = occupation + getattr(item, 'AdditionalOccupation', Decimal(0))
        
        # Set additional occupation if needed
        if hasattr(item, 'AdditionalOccupation') and item.AdditionalOccupation > 0:
            if hasattr(mounted_product, 'SetAdditionalOccupation'):
                mounted_product.SetAdditionalOccupation(item.AdditionalOccupation)
            else:
                mounted_product.AdditionalOccupation = item.AdditionalOccupation
        
        # Find or create MountedSpace
        mounted_space = self._add_mounted_product_to_mounted_space(space, order, quantity, mounted_product, 0)
        
        # Increase occupation (with real occupation)
        if hasattr(mounted_space, 'IncreaseOccupation'):
            mounted_space.IncreaseOccupation(real_occupation)
        else:
            current_occ = getattr(mounted_space, 'Occupation', Decimal(0))
            mounted_space.Occupation = current_occ + real_occupation
        
        # Subtract item amount
        if hasattr(item, 'SubtractAmount'):
            item.SubtractAmount(quantity)
        else:
            item.AmountRemaining = max(0, getattr(item, 'AmountRemaining', 0) - quantity)
        
        # Set ballast on first pallet
        if ballast > 0:
            first_pallet = None
            if hasattr(mounted_space, 'GetFirstPallet'):
                first_pallet = mounted_space.GetFirstPallet()
            elif hasattr(mounted_space, 'Containers') and len(mounted_space.Containers) > 0:
                first_pallet = mounted_space.Containers[0]
            
            if first_pallet is not None and hasattr(first_pallet, 'SetBallast'):
                first_pallet.SetBallast(ballast)
        
        # Subtract client quantity
        if hasattr(item, 'SubtractClientQuantity'):
            item.SubtractClientQuantity(customer, quantity)
        
        return mounted_space

    def PlaceNonPalletizedItemsOnAlreadyOccupiedPallet(self, order: "Order", space: "Space") -> Optional["MountedSpace"]:
        """snake_case alias for PlaceNonPalletizedOnOccupied"""
        return self.place_non_palletized_on_occupied(order, space)
    
    def place_non_palletized_on_occupied(self, order: "Order", space: "Space") -> Optional["MountedSpace"]:
        """Port of C# PlaceNonPalletizedItemsOnAlreadyOccupiedPallet logic.

        Steps:
          - limit context to given order/space
          - verify group limits via DomainOperations
          - create a snapshot limited to the space and run the route rules chain
          - if route produced a mounted space, attempt to add each mounted product
        """
        # log start
        try:
            self.add_execution_log(f"Executando Metodo - PlaceNonPalletizedItemsOnAlreadyOccupiedPallet")
        except Exception:
            pass

        # apply filters if available (Route/AS contexts have these fluent setters)
        if hasattr(self, 'WithOnlyOrder'):
            try:
                self.WithOnlyOrder(order)
            except Exception:
                pass
        if hasattr(self, 'WithOnlySpace'):
            try:
                self.WithOnlySpace(space)
            except Exception:
                pass

        # candidate items with remaining amount
        try:
            items = self.GetItemsWithAmountRemaining()
        except Exception:
            items = [i for i in self.GetItems() if getattr(i, 'AmountRemaining', getattr(i, 'amount_remaining', 0)) > 0]

        mounted_space = self.GetMountedSpace(space)
        # group limit check
        try:
            if self.DomainOperations.ReachedGroupLimit(self, mounted_space) and not any(self.CanBeAssociate(mounted_space, it) for it in items):
                try:
                    self.add_execution_log("Não existe opção para incluir os itens do pedido")
                except Exception:
                    pass
                if hasattr(self, 'ClearFilters'):
                    try:
                        self.ClearFilters()
                    except Exception:
                        pass
                return None
        except Exception:
            # ignore domain op failures and continue
            pass

        # create snapshot restricted to this space (parity with C# CreateSnapshot(space))
        try:
            snapshot = self.CreateSnapshot(spaces=[space])
        except Exception:
            snapshot = self.CreateSnapshot(spaces=[space])

        route_context = self.Snapshot or snapshot

        # build & execute route rules chain
        try:
            from ..factories.route_rule_factories import RouteRuleFactories
            route_rules = RouteRuleFactories().create_route_chain()
            returned_context = route_rules.execute_chain(route_context)
        except Exception:
            returned_context = route_context

        # get first mounted space produced by route chain
        returned_mounted_space = None
        try:
            returned_mounted_space = next(iter(returned_context.MountedSpaces), None)
        except Exception:
            try:
                lst = returned_context.MountedSpaces.ToList() if hasattr(returned_context.MountedSpaces, 'ToList') else list(returned_context.MountedSpaces)
                returned_mounted_space = lst[0] if lst else None
            except Exception:
                returned_mounted_space = None

        if not returned_mounted_space:
            try:
                self.add_execution_log("Nao foi possivel paletizar os itens nao paletizados no calculo de rota.")
            except Exception:
                pass
            if hasattr(self, 'ClearFilters'):
                try:
                    self.ClearFilters()
                except Exception:
                    pass
            return None

        # clear filters in original context
        if hasattr(self, 'ClearFilters'):
            try:
                self.ClearFilters()
            except Exception:
                pass

        target_mounted_space = self.GetMountedSpace(space)

        # for each mounted product on the returned mounted space, try to add to real context
        try:
            first_pallet = returned_mounted_space.GetFirstPallet()
            products = first_pallet.GetProducts() if hasattr(first_pallet, 'GetProducts') else (first_pallet.Products if hasattr(first_pallet, 'Products') else [])
        except Exception:
            products = []

        for mp in list(products):
            try:
                fc = self.FactorConverter if getattr(self, 'FactorConverter', None) is not None else FactorConverter()
                space_size = getattr(space, 'Size', getattr(space, 'size', 0))
                # pallet_setting for occupation calc
                ps = None
                try:
                    itm = getattr(mp, 'Item', None)
                    prod = getattr(itm, 'Product', None) if itm is not None else getattr(mp, 'Product', None)
                    ps = getattr(prod, 'PalletSetting', None) if prod is not None else None
                except Exception:
                    ps = None

                source_occupation = None
                try:
                    source_occupation = self.FactorConverter.occupation(getattr(mp, 'Amount', getattr(mp, 'amount', 0)), space_size, ps, getattr(mp, 'Item', None), self.get_setting('OccupationAdjustmentToPreventExcessHeight', False))
                except Exception:
                    try:
                        source_occupation = fc.occupation(getattr(mp, 'Amount', getattr(mp, 'amount', 0)), space_size, ps, getattr(mp, 'Item', None), self.get_setting('OccupationAdjustmentToPreventExcessHeight', False))
                    except Exception:
                        source_occupation = Decimal(0)

                if target_mounted_space is None or getattr(target_mounted_space, 'OccupationRemaining', getattr(target_mounted_space, 'occupation_remaining', 0)) >= source_occupation:
                    # find item in order matching product
                    item = None
                    try:
                        for it in order.Items:
                            try:
                                if getattr(it, 'Product', None) == getattr(mp, 'Product', None):
                                    item = it
                                    break
                            except Exception:
                                continue
                    except Exception:
                        item = None

                    if item is None:
                        continue

                    # check domain can add
                    try:
                        can_add = self.DomainOperations.CanAdd(self, space, item, getattr(mp, 'Amount', getattr(mp, 'amount', 0)))
                    except Exception:
                        can_add = True

                    if not can_add:
                        continue

                    first_layer = target_mounted_space.GetNextLayer() if target_mounted_space is not None and hasattr(target_mounted_space, 'GetNextLayer') else 0
                    try:
                        quantity_of_layer = item.Product.GetQuantityOfLayerToSpace(getattr(space, 'Size', getattr(space, 'size', 0)), getattr(mp, 'Amount', getattr(mp, 'amount', 0)))
                    except Exception:
                        try:
                            quantity_of_layer = item.product.get_quantity_of_layer_to_space(getattr(space, 'size', getattr(space, 'Size', 0)), getattr(mp, 'amount', getattr(mp, 'Amount', 0)))
                        except Exception:
                            quantity_of_layer = int(getattr(mp, 'Amount', getattr(mp, 'amount', 0)) or 0)

                    # log and add
                    try:
                        side = getattr(space, 'Side', getattr(space, 'side', '?'))
                        number = getattr(space, 'Number', getattr(space, 'number', '?'))
                        self.add_execution_log(f"Adicionando o Item {getattr(item, 'Code', getattr(item, 'code', '?'))}, quantidade {getattr(mp, 'Amount', getattr(mp, 'amount', 0))} no Palete{number} / {side}")
                    except Exception:
                        pass

                    try:
                        self.AddProduct(space, item, getattr(mp, 'Amount', getattr(mp, 'amount', 0)), first_layer, quantity_of_layer, source_occupation)
                    except Exception:
                        try:
                            self.add_product(space, item, getattr(mp, 'Amount', getattr(mp, 'amount', 0)), source_occupation)
                        except Exception:
                            pass
            except Exception as e:
                print(f"Erro ao adicionar produto nao paletizado no palete ocupado: {e}")

        return target_mounted_space

    def getItemByCodeAllSpaces(self, code: int) -> Optional["Item"]:
        return ItemList(self.get_all_products()).getByCodeItem(code)

    def getItemByCodeAllItems(self, code: int) -> Optional["Item"]:
        return ItemList(self.GetAllItems()).getByCodeItem(code)
    
    def _add_mounted_product_to_mounted_space(self, space: "Space", order: Optional["Order"], quantity: int, mounted_product: "MountedProduct", package: int = 0) -> "MountedSpace":
        """
        C#: AddMountedProductToMountedSpace - Helper to find/create mounted space and add product.
        
        Mirrors C# RuleContext.AddMountedProductToMountedSpace:
        1. Search for existing MountedSpace by space.Number and space.Side
        2. Create new MountedSpace if not found
        3. Get or create Container
        4. Add product to container
        5. Return MountedSpace
        
        Args:
            space: Space to add product to
            order: Order that contains the item
            quantity: Quantity to add
            mounted_product: MountedProduct to add
            package: Package number (default 0)
            
        Returns:
            MountedSpace where product was added
        """
        from .container import Container
        
        # Search for existing MountedSpace by Space (comparing by Number and Side)
        # existing_mounted_space = None
        # for ms in self._mounted_spaces:
        #     ms_space = getattr(ms, 'Space', None)
        #     if ms_space is not None:
        #         # Compare by Number and Side (like C# does)
        #         ms_number = getattr(ms_space, 'Number', None)
        #         ms_side = getattr(ms_space, 'Side', None)
        #         space_number = getattr(space, 'Number', None)
        #         space_side = getattr(space, 'Side', None)
                
        #         if ms_number == space_number and ms_side == space_side:
        #             existing_mounted_space = ms
        #             break
        
        # Search for existing MountedSpace by Space (comparing by Number and Side)
        existing_mounted_space = None
        for ms in self._mounted_spaces:
            ms_space = getattr(ms, 'Space', None)
            if ms_space is space:
                existing_mounted_space = ms
                break
            if ms_space is not None:
                # Compare by Number and Side (like C# does)
                ms_number = getattr(ms_space, 'Number', None)
                ms_side = getattr(ms_space, 'Side', None)
                space_number = getattr(space, 'Number', None)
                space_side = getattr(space, 'Side', None)

                if ms_number == space_number and ms_side == space_side:
                    existing_mounted_space = ms
                    break
        # Create new MountedSpace if not found
        if existing_mounted_space is None:
            mounted_space = MountedSpace(space=space, order=order)
            exists_mounted_space = False
        else:
            mounted_space = existing_mounted_space
            exists_mounted_space = True
        
        # Get or create Container
        containers = getattr(mounted_space, 'Containers', [])
        if len(containers) > 0:
            container = containers[0]
            exists_container = True
        else:
            container = Container()
            exists_container = False
        
        # Add mounted product to container
        if hasattr(container, 'AddMountedProduct'):
            container.AddMountedProduct(mounted_product, quantity, package)
        else:
            # Fallback: add to products list
            products = getattr(container, 'Products', [])
            if not hasattr(container, 'Products'):
                container.Products = []
                products = container.Products
            products.append(mounted_product)

        # If container has no ProductBase yet, set it from the mounted product's Product
        try:
            current_pb = getattr(container, 'ProductBase', None)
            mp_product = getattr(mounted_product, 'Product', getattr(mounted_product, 'product', None))
            if (current_pb is None) and (mp_product is not None):
                if hasattr(container, 'SetProductBase'):
                    try:
                        container.SetProductBase(mp_product)
                    except Exception:
                        try:
                            container.ProductBase = mp_product
                        except Exception:
                            pass
                else:
                    try:
                        container.ProductBase = mp_product
                    except Exception:
                        pass
        except Exception:
            pass
        
        # Add container to mounted space if new
        if not exists_container:
            if hasattr(mounted_space, 'AddContainer'):
                mounted_space.AddContainer(container)
            else:
                if not hasattr(mounted_space, 'Containers'):
                    mounted_space.Containers = []
                mounted_space.Containers.append(container)
        
        # Add mounted space to context if new
        if not exists_mounted_space:
            self._mounted_spaces.append(mounted_space)
        
        # Set order if not set
        if hasattr(mounted_space, 'Order') and mounted_space.Order is None:
            if hasattr(mounted_space, 'SetOrder'):
                mounted_space.SetOrder(order)
            else:
                mounted_space.Order = order
        # self._spaces = [s for s in self._spaces if s is not space]
        self.removeSpace(space)

        return mounted_space

    def removeSpace(self, space: "Space"):
        """Remove a Space from the context's Spaces list."""
        try:
            self._spaces.remove(space)
        except ValueError:
            self._spaces = [s for s in self._spaces if s is not space]

    def type_context(self, type_num: int, **kwargs) -> "Context":
        tipo_map = {1: "Rota", 2: "AS", 3: "CrossDocking", 4: "Mixed", 5: "T4"}
        return tipo_map.get(type_num, "Desconhecido")
    
    @staticmethod
    def create_context_for_type(self, type_num: int, **kwargs) -> "Context":
        """Create a concrete Context subclass based on a numeric type code.

        This helper maps the provided `type_num` to a context kind and instantiates
        the appropriate subclass (RouteRuleContext, ASRuleContext, MixedRuleContext, T4RuleContext)
        when available in this module. If no match is found, returns a plain Context.

        Accepts the same constructor kwargs used by Context: orders, spaces, mounted_spaces,
        settings, domain_operations, factor_converter.
        """
        kind = self.type_context(type_num)

        # Lookup subclass from module globals; fall back to base Context if missing
        cls_map = {
            "Rota": globals().get("RouteRuleContext", Context),
            "AS": globals().get("ASRuleContext", Context),
            "CrossDocking": globals().get("CrossDockingRuleContext", globals().get("RouteRuleContext", Context)),
            "Mixed": globals().get("MixedRuleContext", Context),
            "T4": globals().get("T4RuleContext", Context),
        }

        ctx_cls = cls_map.get(kind, Context)
        return ctx_cls(
            orders=kwargs.get("orders"),
            spaces=kwargs.get("spaces"),
            mounted_spaces=kwargs.get("mounted_spaces"),
            settings=kwargs.get("settings"),
            domain_operations=kwargs.get("domain_operations"),
            factor_converter=kwargs.get("factor_converter"),
        )

    def SetMapNumber(self, number: int):
        self.MapNumber = int(number)

    def GetMapNumber(self) -> Optional[int]:
        return self.MapNumber
    
    def add_execution_log(self, message: str):
        print(message)
        logger.log(message)

    def GetOrderFilter(self) -> Optional[Callable[[Any], bool]]:
        """
        Return the current order filter callable used by Route/AS contexts
        (parity with RouteRuleContext._order_filter). Defaults to None.
        """
        return getattr(self, "_order_filter", None)

    def GetOnlyOrder(self) -> Optional[Any]:
        """
        Return the 'only order' filter (parity with RouteRuleContext._only_order).
        """
        return getattr(self, "_only_order", None)

    def GetOnlySpace(self) -> Optional[Any]:
        """
        Return the 'only space' filter (parity with RouteRuleContext._only_space).
        """
        return getattr(self, "_only_space", None)

    # snake_case aliases
    def get_order_filter(self) -> Optional[Callable[[Any], bool]]:
        return self.GetOrderFilter()

    def get_only_order(self) -> Optional[Any]:
        return self.GetOnlyOrder()

    def get_only_space(self) -> Optional[Any]:
        return self.GetOnlySpace()

    # ============================================================
    #  MERGE IN-PLACE DE ORDERS NO CONTEXT (mutação direta)
    # ============================================================

    def merge_orders_in_place(self, marketplace_created_itens=None, marketplace_code_itens=None) -> Order:
        """
        Merge todas as orders do context._orders em uma única order.
        Substitui diretamente context._orders por uma lista com apenas a order consolidada.
        Guarda backup para reversão posterior em context._orders_backup.
        """
        # guarda backup caso precise reverter
        self._orders_backup = self._orders.copy()
        if marketplace_created_itens is None:
            marketplace_created_itens = []
        if marketplace_code_itens is None:
            marketplace_code_itens = set()

        all_items = []

        for order in self._orders:
            for item in order._items:
                if str(item.Code) not in marketplace_code_itens:
                    # salva metadata reversível dentro do próprio item
                    item._source_order_identifier = order._identifier
                    item._source_order_delivery = order._delivery_order
                    item._source_order_support_point = order._support_point
                    item._source_order_map_number = order._map_number
                    item._source_order_license_plate = order._license_plate
                    all_items.append(item)

        # Ordena os itens de forma equivalente ao C#:
        # orderedItems = allItems.OrderByDescending(x => x.Product is IReturnable)
        #                .ThenBy(x => x.Product.PackingGroup?.GroupCode)
        #                .ThenBy(x => x.Product.PackingGroup?.SubGroupCode)
        ordered_items =  ItemList(all_items).ordered_by_returnables_and_group_sub_group()
        
        # mescla itens iguais mantendo metadata (usa ordem do C#)
        merged_items = self.merge_items_by_code_with_metadata(ordered_items)

        merged_items[:0] = marketplace_created_itens

        # cria a order consolidada
        consolidated = Order(
            DeliveryOrder=999999,
            Identifier=999999,
            QuantityOfPalletsNeeded=0,
            QuantityOfPalletsNeededRounded=0,
            AdditionalSpaces=0,
            SupportPoint="MERGED",
            MapNumber="MERGED",
            LicensePlate="",
            items=merged_items,
        )

        # substitui orders do contexto pela consolidada
        self._orders = [consolidated]

        return consolidated


    # ============================================================
    #  FUNÇÃO AUXILIAR: merge itens mantendo metadata
    # ============================================================

    def merge_items_by_code_with_metadata(self, items: list[Item]) -> list[Item]:
        result = {}

        for item in items:
            key = f"{getattr(item, '_code', '')}|{getattr(item, '_map_number', '') or ''}|{getattr(item, '_license_plate', '') or ''}"

            if key not in result:
                item_factor = item.Factor
                if item_factor == 0 and item._product is not None:
                    item_factor = getattr(item, 'Factor', 0)

                clone = Item(
                    Code=item._code,
                    Amount=item._amount,
                    AmountRemaining=item._amount_remaining,
                    DetachedAmount=item._detached_amount,
                    UnitAmount=getattr(item, '_unit_amount', 0),
                    LayersRemaining=getattr(item, '_layers_remaining', 0),
                    Splitted=getattr(item, '_splitted', False),
                    OcpDefaultPerUni42=getattr(item, '_ocp_default_per_uni42', 0),
                    Product=item._product,
                    LicensePlate=item._license_plate,
                    MapNumber=item._map_number,
                    Customer=getattr(item, '_customer', None),
                    ClientQuantity=dict(getattr(item, '_client_quantity', {})),
                    DeliveryOrderSafeSide=dict(getattr(item, '_delivery_order_safe_side', {})),
                    DeliveryOrdersClient=dict(getattr(item, '_delivery_orders_client', {})),
                    AmountPerContainer=getattr(item, '_amount_per_container', 0),
                    Factor=item.Factor,
                    AdditionalOccupation=getattr(item, '_additional_occupation', 0),
                    Realocated=getattr(item, '_realocated', False),
                )

                clone._delivery_orders = dict(getattr(item, '_delivery_orders', {}))
                clone._delivery_orders_detached = dict(getattr(item, '_delivery_orders_detached', {}))

                if not hasattr(clone, '_factor') or clone._factor == 0:
                    clone._factor = item_factor

                clone._sources = [{
                    "identifier": item._source_order_identifier,
                    "delivery": item._source_order_delivery,
                    "support": item._source_order_support_point,
                    "map": item._source_order_map_number,
                    "plate": item._source_order_license_plate,
                    "amount": item._amount,
                    "amount_remaining": item._amount_remaining,
                    "detached_amount": item._detached_amount,
                    "client_quantity": dict(getattr(item, '_client_quantity', {})),
                    "delivery_orders": dict(getattr(item, '_delivery_orders', {})),
                    "delivery_orders_detached": dict(getattr(item, '_delivery_orders_detached', {})),
                }]

                result[key] = clone
            else:
                merged = result[key]
                merged._amount += item._amount
                merged._amount_remaining += item._amount_remaining
                merged._detached_amount += item._detached_amount
                merged._unit_amount += getattr(item, '_unit_amount', 0)

                item_client_qty = getattr(item, '_client_quantity', {})
                for delivery_order, qty in item_client_qty.items():
                    merged._client_quantity[delivery_order] = merged._client_quantity.get(delivery_order, 0) + qty

                item_delivery_orders = getattr(item, '_delivery_orders', {})
                for delivery_order, qty in item_delivery_orders.items():
                    merged._delivery_orders[delivery_order] = merged._delivery_orders.get(delivery_order, 0) + qty

                item_delivery_orders_detached = getattr(item, '_delivery_orders_detached', {})
                for delivery_order, qty in item_delivery_orders_detached.items():
                    merged._delivery_orders_detached[delivery_order] = merged._delivery_orders_detached.get(delivery_order, 0) + qty

                item_safe_side = getattr(item, '_delivery_order_safe_side', {})
                for delivery_order, side in item_safe_side.items():
                    if delivery_order not in merged._delivery_order_safe_side:
                        merged._delivery_order_safe_side[delivery_order] = side

                item_orders_client = getattr(item, '_delivery_orders_client', {})
                for delivery_order, client in item_orders_client.items():
                    if delivery_order not in merged._delivery_orders_client:
                        merged._delivery_orders_client[delivery_order] = client

                merged._sources.append({
                    "identifier": item._source_order_identifier,
                    "delivery": item._source_order_delivery,
                    "support": item._source_order_support_point,
                    "map": item._source_order_map_number,
                    "plate": item._source_order_license_plate,
                    "amount": item._amount,
                    "amount_remaining": item._amount_remaining,
                    "detached_amount": item._detached_amount,
                    "client_quantity": dict(getattr(item, '_client_quantity', {})),
                    "delivery_orders": dict(getattr(item, '_delivery_orders', {})),
                    "delivery_orders_detached": dict(getattr(item, '_delivery_orders_detached', {})),
                })

        return list(result.values())

    def merge_items_by_code_with_metadata2(self, items: list[Item]) -> list[Item]:
        result = {}

        for item in items:
            code = item._code

            if code not in result:
                # CRITICAL: Factor pode estar tanto em item._factor quanto em item.Product.Factor
                item_factor = item.Factor 
                if item_factor == 0 and item._product is not None:
                    item_factor = getattr(item, 'Factor', 0)
                
                clone = Item(
                    Code=item._code,
                    Amount=item._amount,
                    AmountRemaining=item._amount_remaining,
                    DetachedAmount=item._detached_amount,
                    UnitAmount=getattr(item, '_unit_amount', 0),
                    LayersRemaining=getattr(item, '_layers_remaining', 0),
                    Splitted=getattr(item, '_splitted', False),
                    OcpDefaultPerUni42=getattr(item, '_ocp_default_per_uni42', 0),
                    Product=item._product,
                    LicensePlate=item._license_plate,
                    MapNumber=item._map_number,
                    Customer=getattr(item, '_customer', None),
                    ClientQuantity=dict(getattr(item, '_client_quantity', {})),
                    DeliveryOrderSafeSide=dict(getattr(item, '_delivery_order_safe_side', {})),
                    DeliveryOrdersClient=dict(getattr(item, '_delivery_orders_client', {})),
                    AmountPerContainer=getattr(item, '_amount_per_container', 0),
                    Factor=item.Factor,
                    AdditionalOccupation=getattr(item, '_additional_occupation', 0),
                    Realocated=getattr(item, '_realocated', False),
                )
                
                # CRITICAL: Copiar os dicionários de delivery orders que são perdidos no construtor
                clone._delivery_orders = dict(getattr(item, '_delivery_orders', {}))
                clone._delivery_orders_detached = dict(getattr(item, '_delivery_orders_detached', {}))
                
                # CRITICAL: Garantir que _factor está setado corretamente (pode ser necessário se property setter falhar)
                if not hasattr(clone, '_factor') or clone._factor == 0:
                    clone._factor = item_factor

                clone._sources = [{
                    "identifier": item._source_order_identifier,
                    "delivery": item._source_order_delivery,
                    "support": item._source_order_support_point,
                    "map": item._source_order_map_number,
                    "plate": item._source_order_license_plate,
                    "amount": item._amount,
                    "amount_remaining": item._amount_remaining,
                    "detached_amount": item._detached_amount,
                    "client_quantity": dict(getattr(item, '_client_quantity', {})),
                    "delivery_orders": dict(getattr(item, '_delivery_orders', {})),
                    "delivery_orders_detached": dict(getattr(item, '_delivery_orders_detached', {})),
                }]

                result[code] = clone
            else:
                merged = result[code]
                merged._amount += item._amount
                merged._amount_remaining += item._amount_remaining
                merged._detached_amount += item._detached_amount
                merged._unit_amount += getattr(item, '_unit_amount', 0)
                
                # CRITICAL: Factor não deve ser alterado no merge - já foi definido no clone inicial
                # Factor é uma propriedade do produto (unidades por caixa), todos os items com mesmo Code têm o mesmo Factor
                # Não fazemos nada aqui, o Factor do clone já está correto
                
                # CRITICAL: Outros campos não acumuláveis também já estão corretos no clone
                # LicensePlate, MapNumber, LayersRemaining, etc já foram copiados do primeiro item
                
                # CRITICAL: merge ClientQuantity dictionaries by summing quantities per delivery order
                item_client_qty = getattr(item, '_client_quantity', {})
                for delivery_order, qty in item_client_qty.items():
                    merged._client_quantity[delivery_order] = merged._client_quantity.get(delivery_order, 0) + qty
                
                # CRITICAL: merge _delivery_orders dictionaries
                item_delivery_orders = getattr(item, '_delivery_orders', {})
                for delivery_order, qty in item_delivery_orders.items():
                    merged._delivery_orders[delivery_order] = merged._delivery_orders.get(delivery_order, 0) + qty
                
                # CRITICAL: merge _delivery_orders_detached dictionaries
                item_delivery_orders_detached = getattr(item, '_delivery_orders_detached', {})
                for delivery_order, qty in item_delivery_orders_detached.items():
                    merged._delivery_orders_detached[delivery_order] = merged._delivery_orders_detached.get(delivery_order, 0) + qty
                
                # Merge DeliveryOrderSafeSide (usa o último valor para cada delivery order)
                item_safe_side = getattr(item, '_delivery_order_safe_side', {})
                for delivery_order, side in item_safe_side.items():
                    if delivery_order not in merged._delivery_order_safe_side:
                        merged._delivery_order_safe_side[delivery_order] = side
                
                # Merge DeliveryOrdersClient (usa o último valor para cada delivery order)
                item_orders_client = getattr(item, '_delivery_orders_client', {})
                for delivery_order, client in item_orders_client.items():
                    if delivery_order not in merged._delivery_orders_client:
                        merged._delivery_orders_client[delivery_order] = client
                
                merged._sources.append({
                    "identifier": item._source_order_identifier,
                    "delivery": item._source_order_delivery,
                    "support": item._source_order_support_point,
                    "map": item._source_order_map_number,
                    "plate": item._source_order_license_plate,
                    "amount": item._amount,
                    "amount_remaining": item._amount_remaining,
                    "detached_amount": item._detached_amount,
                    "client_quantity": dict(getattr(item, '_client_quantity', {})),
                    "delivery_orders": dict(getattr(item, '_delivery_orders', {})),
                    "delivery_orders_detached": dict(getattr(item, '_delivery_orders_detached', {})),
                })

        return list(result.values())


    # ============================================================
    #  REVERSE: restaura orders originais do backup
    # ============================================================

    # def unmerge_orders_in_place(self):
    #     """
    #     Reverte a operação de merge, restaurando as orders originais do backup.
    #     """
    #     if not hasattr(self, "_orders_backup"):
    #         raise RuntimeError("Nenhum backup encontrado. Merge não foi feito ou já foi revertido.")

    #     # restaura a lista original
    #     self._orders = self._orders_backup
    #     del self._orders_backup  # remove backup após reversão
        
    def unmerge_orders_in_place(self):
        """
        Reverte parcialmente o merge: restaura SOMENTE metadados escalares das orders
        (Identifier, DeliveryOrder, SupportPoint, MapNumber, LicensePlate).
        Não altera a lista de items de nenhuma order.
        """
        if not hasattr(self, "_orders_backup"):
            raise RuntimeError("Nenhum backup encontrado. Merge não foi feito ou já foi revertido.")

        backup = getattr(self, "_orders_backup") or []
        current = list(getattr(self, "_orders", []) or [])

        keys = ("Identifier", "DeliveryOrder", "SupportPoint", "MapNumber", "LicensePlate")

        # helper: extrai metadata padronizada de uma order
        def _meta_from(o):
            return {
                k: getattr(o, k, None)
                or getattr(o, k.lower(), None)
                or getattr(o, k[0].lower() + k[1:], None)
                for k in keys
            }

        # helper: aplica metadado em uma order atual (tenta variantes de nome)
        def _apply_meta(target, meta):
            name_variants = {
                "Identifier": ["Identifier", "identifier"],
                "DeliveryOrder": ["DeliveryOrder", "delivery_order", "deliveryOrder"],
                "SupportPoint": ["SupportPoint", "support_point", "supportPoint"],
                "MapNumber": ["MapNumber", "map_number", "mapNumber"],
                "LicensePlate": ["LicensePlate", "license_plate", "licensePlate"],
            }
            for k, v in meta.items():
                if v is None:
                    continue
                for attr_name in name_variants.get(k, [k, k.lower()]):
                    try:
                        setattr(target, attr_name, v)
                        break
                    except Exception:
                        try:
                            # tentativa alternativa reduzida (atributo público)
                            if hasattr(target, attr_name):
                                setattr(target, attr_name, v)
                                break
                        except Exception:
                            continue

        # build meta list from backup
        backup_meta = [_meta_from(b) for b in backup]

        try:
            # 1) se as contagens batem, aplica por índice (mais simples e determinístico)
            if len(current) == len(backup_meta) and len(current) > 0:
                for cur, meta in zip(current, backup_meta):
                    _apply_meta(cur, meta)
                return

            # 2) se há uma única ordem atual (merge consolidado), agregamos metadados do backup
            if len(current) == 1 and backup_meta:
                aggregate = {}
                for k in keys:
                    # encontra primeiro valor não-nulo no backup para cada campo
                    val = next((m[k] for m in backup_meta if m.get(k) not in (None, "")), None)
                    aggregate[k] = val
                _apply_meta(current[0], aggregate)
                return

            # 3) fallback: tenta casar por MapNumber, Identifier ou LicensePlate
            lookup = {}
            for m in backup_meta:
                for probe in ("MapNumber", "Identifier", "LicensePlate", "DeliveryOrder"):
                    v = m.get(probe)
                    if v is None:
                        continue
                    lookup_key = (probe, str(v))
                    if lookup_key not in lookup:
                        lookup[lookup_key] = m

            for cur in current:
                matched = None
                for probe in ("MapNumber", "Identifier", "LicensePlate", "DeliveryOrder"):
                    cur_val = getattr(cur, probe, None) or getattr(cur, probe.lower(), None) or getattr(cur, probe[0].lower() + probe[1:], None)
                    if cur_val is None:
                        continue
                    lk = (probe, str(cur_val))
                    if lk in lookup:
                        matched = lookup[lk]
                        break
                if matched:
                    _apply_meta(cur, matched)

        finally:
            # removemos o backup (unmerge considerado consumido)
            try:
                del self._orders_backup
            except Exception:
                try:
                    self._orders_backup = None
                except Exception:
                    pass
                
    # def ReattachOriginalOrdersToMountedProducts(self, use_orders_backup: bool = True) -> int:
    #     """
    #     Reatribui a referência `Order` em cada MountedProduct com base, na ordem:
    #     1) restauração de orders via `_orders_backup` (se `use_orders_backup` e backup existir);
    #     2) metadados `item._sources` (primeira origem que casar com uma Order atual);
    #     3) busca por `Item.Code` dentro de cada Order como fallback;
    #     4) se nada casar, deixa como estava.

    #     Retorna o número de mounted-products atualizados.
    #     """
    #     assigned = 0

    #     # opcional: restaura orders a partir do backup para facilitar o match
    #     if use_orders_backup and getattr(self, "_orders_backup", None):
    #         try:
    #             self.unmerge_orders_in_place()
    #         except Exception:
    #             pass

    #     orders_list = getattr(self, "Orders", []) or []
    #     mspaces = list(getattr(self, "_mounted_spaces", []) or [])

    #     for ms in mspaces:
    #         containers = getattr(ms, "Containers", []) or []
    #         for c in containers:
    #             products = getattr(c, "Products", []) or []
    #             for mp in products:
    #                 # obter o item associado ao mounted-product
    #                 item = getattr(mp, "Item", None) or getattr(mp, "item", None)
    #                 if item is None:
    #                     continue

    #                 order = None

    #                 # 1) tenta por item._sources (cada source é dict com MapNumber/DocumentNumber/LicensePlate)
    #                 sources = getattr(item, "_sources", None) or getattr(item, "sources", None)
    #                 if isinstance(sources, list) and sources:
    #                     for src in sources:
    #                         if not isinstance(src, dict):
    #                             continue
    #                         # MapNumber / Number
    #                         mapnum = src.get("MapNumber") or src.get("Number") or src.get("MapNumberId")
    #                         if mapnum is not None:
    #                             for o in orders_list:
    #                                 if getattr(o, "MapNumber", None) == mapnum or getattr(o, "Number", None) == mapnum:
    #                                     order = o
    #                                     break
    #                         if order:
    #                             break
    #                         # DocumentNumber
    #                         docnum = src.get("DocumentNumber") or src.get("documentNumber")
    #                         if docnum is not None:
    #                             for o in orders_list:
    #                                 dnums = getattr(o, "DocumentNumbers", None) or getattr(o, "DocumentNumber", None)
    #                                 if isinstance(dnums, (list, tuple)):
    #                                     if docnum in dnums:
    #                                         order = o
    #                                         break
    #                                 elif dnums == docnum:
    #                                     order = o
    #                                     break
    #                         if order:
    #                             break
    #                         # LicensePlate / VehiclePlate
    #                         plate = src.get("LicensePlate") or src.get("VehiclePlate") or src.get("VehiclePlateNumber")
    #                         if plate is not None:
    #                             for o in orders_list:
    #                                 if getattr(o, "VehiclePlate", None) == plate or getattr(o, "LicensePlate", None) == plate:
    #                                     order = o
    #                                     break
    #                         if order:
    #                             break

    #                 # 2) fallback: achar pela presença do item (Code) nas orders
    #                 if order is None:
    #                     item_code = getattr(item, "Code", None) or getattr(item, "code", None)
    #                     if item_code is not None:
    #                         for o in orders_list:
    #                             for oi in getattr(o, "Items", getattr(o, "items", []) or []):
    #                                 oi_code = getattr(oi, "Code", None) or getattr(oi, "code", None)
    #                                 if oi_code is not None and str(oi_code) == str(item_code):
    #                                     order = o
    #                                     break
    #                             if order:
    #                                 break

    #                 # 3) aplicar se encontrado
    #                 if order is not None:
    #                     try:
    #                         setattr(mp, "Order", order)
    #                     except Exception:
    #                         try:
    #                             mp.Order = order
    #                         except Exception:
    #                             pass
    #                     assigned += 1

    #     return assigned

    def ReattachOriginalOrdersToMountedProducts(self, use_orders_backup: bool = True) -> int:
        """
        Reattach MountedProduct.Order using per-item `_sources` metadata and the
        `_orders_backup` produced by `merge_orders_in_place()`.

        Non-destructive: DOES NOT change item amounts or replace `self._orders`.
        Returns number of mounted-products reassigned.
        """
        assigned = 0
        # nothing to do without backup or mounted products
        backup_orders = getattr(self, "_orders_backup", None) or []
        if not backup_orders:
            return 0

        # build quick lookup from backup orders by several keys
        def _key_candidates(o):
            return {
                ("Identifier", str(getattr(o, "Identifier", getattr(o, "identifier", "")) or "")),
                ("MapNumber", str(getattr(o, "MapNumber", getattr(o, "map_number", "")) or "")),
                ("LicensePlate", str(getattr(o, "LicensePlate", getattr(o, "license_plate", "")) or "")),
                ("DeliveryOrder", str(getattr(o, "DeliveryOrder", getattr(o, "delivery_order", "")) or "")),
            }

        backup_lookup: dict = {}
        for bo in backup_orders:
            for k, v in (_k for _k in [(kk, vv) for kk, vv in [(x[0], x[1]) for x in _key_candidates(bo)]]):
                if v:
                    backup_lookup.setdefault((k, v), bo)

        # normalize sources from item._sources
        def _normalize_source(src: dict) -> dict:
            return {
                "identifier": src.get("identifier") or src.get("Identifier") or src.get("IdentifierId") or src.get("id"),
                "map": src.get("map") or src.get("MapNumber") or src.get("map_number") or src.get("Map"),
                "plate": src.get("plate") or src.get("LicensePlate") or src.get("license_plate"),
                "delivery": src.get("delivery") or src.get("DeliveryOrder") or src.get("delivery_order"),
                "amount": int(src.get("amount") or src.get("amount_remaining") or 0),
            }

        # helper: try match a source to a backup order object
        def _find_order_for_source(src_norm):
            for probe in ("map", "identifier", "plate", "delivery"):
                val = src_norm.get(probe)
                if val in (None, "", 0):
                    continue
                key = (probe.capitalize() if probe != "plate" else ("LicensePlate" if probe == "plate" else probe), str(val))
                # normalize keys used in backup_lookup:
                # e.g., ("MapNumber", "123"), ("Identifier", "321"), ("LicensePlate", "ABC")
                # Accept multiple possible key variants:
                if probe == "map":
                    cand = (("MapNumber", str(val)), ("Map", str(val)))
                elif probe == "identifier":
                    cand = (("Identifier", str(val)),)
                elif probe == "plate":
                    cand = (("LicensePlate", str(val)),)
                elif probe == "delivery":
                    cand = (("DeliveryOrder", str(val)),)
                else:
                    cand = ((probe.capitalize(), str(val)),)

                for c in cand:
                    bo = backup_lookup.get(c)
                    if bo:
                        return bo
            return None

        # iterate mounted-products
        mproducts = []
        try:
            mproducts = self.GetAllProducts()
        except Exception:
            # fallback: try direct attribute
            mspaces = getattr(self, "_mounted_spaces", []) or []
            for ms in mspaces:
                for c in getattr(ms, "Containers", []) or []:
                    for p in getattr(c, "Products", []) or []:
                        mproducts.append(p)

        for mp in (mproducts or []):
            try:
                item = getattr(mp, "Item", getattr(mp, "item", None))
                if item is None:
                    continue
                srcs = getattr(item, "_sources", None) or getattr(item, "sources", None)
                if not srcs:
                    continue
                # collect candidate orders from sources with amounts
                candidates: list[tuple] = []
                for s in srcs:
                    if not isinstance(s, dict):
                        continue
                    sn = _normalize_source(s)
                    bo = _find_order_for_source(sn)
                    if bo:
                        candidates.append((bo, sn.get("amount", 0), sn))

                if not candidates:
                    # fallback: try match by item code presence in backup orders' items
                    it_code = getattr(item, "Code", getattr(item, "_code", None)) or getattr(item, "code", None)
                    found_bo = None
                    if it_code is not None:
                        for bo in backup_orders:
                            for oi in getattr(bo, "Items", getattr(bo, "_items", []) or []):
                                oi_code = getattr(oi, "Code", getattr(oi, "_code", None)) or getattr(oi, "code", None)
                                if oi_code is not None and str(oi_code) == str(it_code):
                                    found_bo = bo
                                    break
                            if found_bo:
                                break
                    if found_bo:
                        try:
                            setattr(mp, "Order", found_bo)
                        except Exception:
                            try:
                                mp.Order = found_bo
                            except Exception:
                                pass
                        # try set MapNumber for convenience
                        try:
                            mp.MapNumber = getattr(found_bo, "MapNumber", getattr(found_bo, "map_number", None))
                        except Exception:
                            pass
                        # restore Customer metadata without triggering ComplexLoad
                        try:
                            cust = getattr(found_bo, "Customer", None) or getattr(found_bo, "customer", None)
                            if cust not in (None, "", 0):
                                try:
                                    # assign backing field directly to avoid setter side-effects
                                    mp.__dict__['_customer'] = int(cust)
                                except Exception:
                                    mp.__dict__['_customer'] = cust
                        except Exception:
                            pass
                        assigned += 1
                        continue

                # determine mp quantity
                mp_qty = getattr(mp, "Amount", getattr(mp, "amount", None))
                try:
                    mp_qty = int(mp_qty) if mp_qty is not None else 0
                except Exception:
                    mp_qty = 0

                # choose best candidate:
                selected = None
                if len(candidates) == 1:
                    selected = candidates[0][0]
                else:
                    # try to find candidate whose source amount >= mp_qty
                    for bo, amt, sn in candidates:
                        if amt >= mp_qty and mp_qty > 0:
                            selected = bo
                            break
                    # otherwise pick candidate with largest amt
                    if selected is None:
                        candidates_sorted = sorted(candidates, key=lambda x: -int(x[1] or 0))
                        if candidates_sorted:
                            selected = candidates_sorted[0][0]

                if selected:
                    try:
                        setattr(mp, "Order", selected)
                    except Exception:
                        try:
                            mp.Order = selected
                        except Exception:
                            pass
                    # also set MapNumber if possible
                    try:
                        mp.MapNumber = getattr(selected, "MapNumber", getattr(selected, "map_number", None))
                    except Exception:
                        pass
                    assigned += 1
            except Exception:
                # best-effort per-mp: ignore failures
                continue

        return assigned

    # snake_case alias
    def reattach_original_orders_to_mounted_products(self, use_orders_backup: bool = True):
        """
        Reverte a operação de merge para fins de metadados em mounted-products.
        Não altera quantidades de items/orders — apenas reatribui/atualiza os
        campos principais da Order referenciada por cada MountedProduct (mp).
        """
        backups = getattr(self, "_orders_backup", None) or []
        if not backups:
            return

        # build lookups
        backup_by_id = {}
        backup_by_key = {}
        for o in backups:
            ident = getattr(o, "Identifier", None) or getattr(o, "Id", None) or getattr(o, "OrderIdentifier", None)
            if ident is not None:
                backup_by_id[str(ident)] = o
            key = (str(getattr(o, "MapNumber", None) or getattr(o, "map_number", None) or ""),
                str(getattr(o, "DeliveryOrder", None) or getattr(o, "delivery_order", None) or ""))
            backup_by_key[key] = o
            lp = getattr(o, "LicensePlate", None) or getattr(o, "license_plate", None) or getattr(o, "VehiclePlate", None)
            if lp:
                backup_by_id.setdefault(("LP:" + str(lp)), o)

        def _normalize_source(src: dict) -> dict:
            # normalize many possible key variants into canonical fields
            return {
                "Identifier": src.get("identifier") or src.get("Identifier") or src.get("OrderIdentifier") or src.get("id") or src.get("Id"),
                "MapNumber": src.get("map") or src.get("MapNumber") or src.get("map_number") or src.get("Map"),
                "LicensePlate": src.get("plate") or src.get("Plate") or src.get("LicensePlate") or src.get("license_plate") or src.get("VehiclePlate"),
                "DeliveryOrder": src.get("delivery") or src.get("DeliveryOrder") or src.get("delivery_order"),
                "Amount": int(src.get("amount") or src.get("Amount") or src.get("amount_remaining") or 0),
            }

        def _find_backup_from_src(ns: dict):
            # try identifier
            ident = ns.get("Identifier")
            if ident not in (None, "", 0):
                bo = backup_by_id.get(str(ident))
                if bo:
                    return bo
            # try license plate
            lp = ns.get("LicensePlate")
            if lp:
                bo = backup_by_id.get("LP:" + str(lp))
                if bo:
                    return bo
            # try map+delivery
            key = (str(ns.get("MapNumber") or ""), str(ns.get("DeliveryOrder") or ""))
            bo = backup_by_key.get(key)
            if bo:
                return bo
            # try match only map
            for k, v in backup_by_key.items():
                if k[0] and ns.get("MapNumber") and str(k[0]) == str(ns.get("MapNumber")):
                    return v
            # try match only delivery
            for k, v in backup_by_key.items():
                if k[1] and ns.get("DeliveryOrder") and str(k[1]) == str(ns.get("DeliveryOrder")):
                    return v
            return None

        mounted_spaces = getattr(self, "MountedSpaces", None) or getattr(self, "mounted_spaces", None) or []
        for ms in mounted_spaces:
            try:
                products = ms.GetProducts()
            except Exception:
                try:
                    products = ms.get_products()
                except Exception:
                    products = getattr(ms, "Products", getattr(ms, "products", [])) or []

            for mp in products:
                # obtain item (mp might itself be item-like)
                item = getattr(mp, "Item", None) or getattr(mp, "Product", None) or mp

                # gather sources
                sources = getattr(item, "_sources", None) or getattr(item, "sources", None) or []
                if not sources:
                    # try older per-item fields
                    src = {}
                    for k in ("OrderIdentifier", "MapNumber", "DeliveryOrder", "SupportPoint", "LicensePlate", "Amount"):
                        v = getattr(item, f"_source_order_{k.lower()}", None) or getattr(item, f"_source_{k.lower()}", None)
                        if v is not None:
                            src[k] = v
                    if src:
                        sources = [src]
                if not sources:
                    continue

                # normalize and pick best source (prefer amount >= mp.Amount)
                normalized = []
                for s in sources:
                    if not isinstance(s, dict):
                        continue
                    ns = _normalize_source(s)
                    normalized.append(ns)

                mp_qty = getattr(mp, "Amount", None) or getattr(mp, "amount", None) or 0
                try:
                    mp_qty = int(mp_qty)
                except Exception:
                    mp_qty = 0

                chosen_ns = None
                # prefer source with amount >= mp_qty
                for ns in normalized:
                    amt = ns.get("Amount", 0) or 0
                    try:
                        if mp_qty > 0 and int(amt) >= int(mp_qty):
                            chosen_ns = ns
                            break
                    except Exception:
                        pass
                if chosen_ns is None:
                    # pick largest amount otherwise
                    if normalized:
                        normalized.sort(key=lambda x: -int(x.get("Amount", 0) or 0))
                        chosen_ns = normalized[0]
                    else:
                        chosen_ns = None

                backup = None
                if chosen_ns:
                    backup = _find_backup_from_src(chosen_ns)

                if backup:
                    # attempt to set whole order object
                    try:
                        mp.Order = backup
                    except Exception:
                        # fallback: update scalar fields on existing mp.Order or create minimal container
                        target = getattr(mp, "Order", None)
                        if target is None:
                            try:
                                class _O: pass
                                o_new = _O()
                                mp.Order = o_new
                                target = o_new
                            except Exception:
                                target = None
                        if target:
                            for attr in ("Identifier", "MapNumber", "DeliveryOrder", "SupportPoint", "LicensePlate"):
                                val = getattr(backup, attr, None) or getattr(backup, attr.lower(), None)
                                if val not in (None, ""):
                                    try:
                                        setattr(target, attr, val)
                                    except Exception:
                                        pass
                    # try set MapNumber on mp for convenience
                    try:
                        mp.MapNumber = getattr(backup, "MapNumber", getattr(backup, "map_number", None))
                    except Exception:
                        pass
                    # restore Customer metadata without triggering ComplexLoad
                    try:
                        cust = getattr(backup, "Customer", None) or getattr(backup, "customer", None)
                        if cust not in (None, "", 0):
                            try:
                                mp.__dict__['_customer'] = int(cust)
                            except Exception:
                                mp.__dict__['_customer'] = cust
                    except Exception:
                        pass
                else:
                    # fallback: try to set scalar fields from chosen source even if not found in backup
                    if chosen_ns:
                        target = getattr(mp, "Order", None)
                        if target is None:
                            try:
                                class _O: pass
                                o_new = _O()
                                mp.Order = o_new
                                target = o_new
                            except Exception:
                                target = None
                        if target:
                            # map keys
                            if chosen_ns.get("Identifier") not in (None, "", 0):
                                try: setattr(target, "Identifier", chosen_ns.get("Identifier")) 
                                except Exception: pass
                            if chosen_ns.get("MapNumber") not in (None, "", 0):
                                try: setattr(target, "MapNumber", chosen_ns.get("MapNumber")) 
                                except Exception: pass
                            if chosen_ns.get("DeliveryOrder") not in (None, "", 0):
                                try: setattr(target, "DeliveryOrder", chosen_ns.get("DeliveryOrder")) 
                                except Exception: pass
                            if chosen_ns.get("LicensePlate") not in (None, "", 0):
                                try: setattr(target, "LicensePlate", chosen_ns.get("LicensePlate")) 
                                except Exception: pass

class RouteRuleContext(Context):
    """
    Port of C# RouteRuleContext : RuleContext
    Adds simple snapshot/from helpers and potential mounted-space filtering.
    """
    def __init__(self, json_path: Optional[Union[str, Path]] = None, config_path: Optional[Union[str, Path]] = None, *args, **kwargs):
        super().__init__(json_path=json_path, config_path=config_path, *args, **kwargs)
        self._only_space = None
        self._only_mounted_space = None
        self._only_order = None
        self._order_filter: Optional[Callable[[Any], bool]] = None
        self._skip_previous_order_spaces_quantity = 0
        self._kind = "Route"
        # mounted-space filter parity with C# RouteRuleContext: default accept-all
        self._mounted_space_filter: Callable[[Any], bool] = (lambda ms: True)

    # fluent setters (C# style)
    def WithOnlySpace(self, space: Any):
        self._only_space = space
        return self

    def WithOnlyMountedSpace(self, mounted_space: Any):
        self._only_mounted_space = mounted_space
        return self

    def WithOnlyOrder(self, order: Any):
        self._only_order = order
        return self

    def WithOrderFilter(self, filter_func: Callable[[Any], bool]):
        self._order_filter = filter_func
        return self

    def SetOrders(self, orders: Iterable[Any]):
        # replace context orders
        self.Orders = list(orders)
        return self

    def ClearOrderFilters(self):
        self._only_order = None
        self._order_filter = None
        return self

    def SetSkipPreviousOrderSpacesQuantity(self, q: int):
        self._skip_previous_order_spaces_quantity = int(q)
        return self
    
    def ClearOrderFilters(self):
        self._only_order = None
        self._order_filter = None
        return self

    def ClearFilters(self):
        """Clear mounted-space filters (parity with C# ClearFilters)."""
        self._mounted_space_filter = lambda ms: True

    def clear_filters(self):
        return self.ClearFilters()

    def WithMountedSpaceFilter(self, predicate: Optional[Callable] = None):
        """Set a mounted-space filter (parity with C# RouteRuleContext.WithMountedSpaceFilter)."""
        self._mounted_space_filter = predicate if predicate is not None else (lambda ms: True)

    # snake_case aliases for RouteRuleContext methods (compatibility)
    def with_only_space(self, space: Any):
        return self.WithOnlySpace(space)

    def with_only_mounted_space(self, mounted_space: Any):
        return self.WithOnlyMountedSpace(mounted_space)

    def with_only_order(self, order: Any):
        return self.WithOnlyOrder(order)

    def with_order_filter(self, filter_func: Callable[[Any], bool]):
        return self.WithOrderFilter(filter_func)

    def set_orders(self, orders: Iterable[Any]):
        return self.SetOrders(orders)

    def clear_order_filters(self):
        return self.ClearOrderFilters()

    def set_skip_previous_order_spaces_quantity(self, q: int):
        return self.SetSkipPreviousOrderSpacesQuantity(q)

    def create_snapshot(self, orders: Optional[Iterable[Any]] = None, spaces: Optional[Iterable[Any]] = None, mounted_spaces: Optional[Iterable[Any]] = None) -> "RouteRuleContext":
        return self.CreateSnapshot(orders=orders, spaces=spaces, mounted_spaces=mounted_spaces)

    @staticmethod
    def from_(context: "RouteRuleContext", orders: Iterable[Any], spaces: Iterable[Any], mounted_spaces: Iterable[Any]) -> "RouteRuleContext":
        return RouteRuleContext.From(context, orders, spaces, mounted_spaces)

    # properties overriding base behavior to apply filters (mirrors C#)
    @property
    def Spaces(self) -> List[Any]:
        if self._only_space is not None:
            return [self._only_space]
        return super().Spaces

    @property
    def Orders(self) -> List[Any]:
        base_orders = super().Orders
        if self._only_order is not None:
            return [o for o in base_orders if o == self._only_order]
        if self._order_filter is not None:
            return [o for o in base_orders if self._order_filter(o)]
        return base_orders

    @Orders.setter
    def Orders(self, value: Iterable["Order"]):
        """Allow assigning Orders (used by snapshot/from and loaders)."""
        try:
            # try to set underlying storage used by base Context
            self._orders = list(value) if value is not None else []
        except Exception:
            # fallback to attribute assignment
            setattr(self, "_orders", list(value) if value is not None else [])

    @property
    def MountedSpaces(self) -> "MountedSpaceList":
        mounted = list(getattr(self, '_mounted_spaces', []) or [])

        # if an explicit only-mounted-space is requested, return it (highest priority)
        if self._only_mounted_space is not None:
            return MountedSpaceList([self._only_mounted_space])

        # apply mounted-space filter first (parity with C# _mountedSpaceFilter behavior)
        filt = getattr(self, '_mounted_space_filter', (lambda ms: True))
        try:
            mounted = [m for m in mounted if filt(m)]
        except Exception:
            # if predicate fails, fall back to unfiltered list
            mounted = list(getattr(self, '_mounted_spaces', []) or [])

        # filter by only_order when present
        if self._only_order is not None:
            filtered = [m for m in mounted if getattr(m, "Order", None) == self._only_order]
            return MountedSpaceList(filtered)

        return MountedSpaceList(mounted)

    @MountedSpaces.setter
    def MountedSpaces(self, value: Iterable[Any]):
        try:
            self._mounted_spaces = list(value) if value is not None else []
        except Exception:
            setattr(self, "_mounted_spaces", list(value) if value is not None else [])

    @property
    def Spaces(self) -> List[Any]:
        if self._only_space is not None:
            return [self._only_space]
        return super().Spaces

    @Spaces.setter
    def Spaces(self, value: Iterable[Any]):
        try:
            self._spaces = list(value) if value is not None else []
        except Exception:
            setattr(self, "_spaces", list(value) if value is not None else [])

    # snapshot / from helpers (basic parity with C# CreateSnapshot / From)
    # def Creat2eSnapshot(self, orders: Optional[Iterable[Any]] = None, spaces: Optional[Iterable[Any]] = None, mounted_spaces: Optional[Iterable[Any]] = None) -> "RouteRuleContext":
    #     snap = deepcopy(self)
    #     if orders is not None:
    #         snap.Orders = list(orders)
    #     if spaces is not None:
    #         snap.Spaces = list(spaces)
    #     if mounted_spaces is not None:
    #         snap.MountedSpaces = list(mounted_spaces)
    #     # Store snapshot for later access
    #     self._snapshot = snap
    #     return snap

    @staticmethod
    def From(context: "RouteRuleContext", orders: Iterable[Any], spaces: Iterable[Any], mounted_spaces: Iterable[Any]) -> "RouteRuleContext":
        snap = deepcopy(context)
        snap.Orders = list(orders)
        snap.Spaces = list(spaces)
        snap.MountedSpaces = list(mounted_spaces)
        return snap


class ASRuleContext(RouteRuleContext):
    """
    Port of C# ASRuleContext: extends RouteRuleContext with AS-specific helpers.
    Implements: WithOnlySpace, WithOnlyMountedSpace, WithOnlyOrder, WithOrderFilter,
    ClearFilters, ClearOrderFilters, SkipPreviousOrderSpacesQuantity, CreateSnapshot overload
    and parity for Spaces/Orders/MountedSpaces properties.
    """
    def __init__(self, json_path: Optional[Union[str, Path]] = None, config_path: Optional[Union[str, Path]] = None, *args, **kwargs):
        super().__init__(json_path=json_path, config_path=config_path, *args, **kwargs)
        # AS-specific flags
        self._only_space = None
        self._only_mounted_space = None
        self._only_order = None
        self._order_filter: Callable[[Any], bool] = (lambda x: True)
        # In C# this is a bool; in python keep numeric/boolean compatibility
        self._skip_previous_order_spaces_quantity = True
        self._kind = "AS"

    # --- getters used by some C# callers ---------------------------------
    def GetOnlySpace(self):
        return self._only_space

    def GetOnlyMountedSpace(self):
        return self._only_mounted_space

    def GetOnlyOrder(self):
        return self._only_order

    def GetOrderFilter(self):
        return self._order_filter

    # --- fluent helpers --------------------------------------------------
    def WithOnlySpace(self, space: Any):
        self._only_space = space
        return self

    def WithOnlyMountedSpace(self, mounted_space: Any):
        self._only_mounted_space = mounted_space
        return self

    def WithOnlyOrder(self, order: Any):
        self._only_order = order
        return self

    def WithOrderFilter(self, filter_func: Callable[[Any], bool]):
        self._order_filter = filter_func or (lambda x: True)
        return self

    def ClearFilters(self):
        self._only_space = None
        self._only_mounted_space = None
        self._only_order = None
        self._order_filter = (lambda x: True)

    def ClearOrderFilters(self):
        self._order_filter = (lambda x: True)

    def SetOrders(self, orders: Iterable[Any]):
        try:
            self._orders = list(orders) if orders is not None else []
        except Exception:
            setattr(self, "_orders", list(orders) if orders is not None else [])

    def SetSkipPreviousOrderSpacesQuantity(self, q: Union[bool, int]):
        # Accept both bool (C# style) and int (python port uses counts elsewhere)
        if isinstance(q, bool):
            self._skip_previous_order_spaces_quantity = q
        else:
            try:
                self._skip_previous_order_spaces_quantity = int(q)
            except Exception:
                self._skip_previous_order_spaces_quantity = bool(q)
        return self

    @property
    def SkipPreviousOrderSpacesQuantity(self):
        return self._skip_previous_order_spaces_quantity

    # --- Orders override -------------------------------------------------
    @property
    def Orders(self) -> List[Any]:
        # If no only-order specified, apply order filter to backing _orders
        if getattr(self, '_only_order', None) is None:
            try:
                return [o for o in self._orders if (self._order_filter or (lambda x: True))(o)]
            except Exception:
                return list(self._orders)

        # only_order present: return the one matching identifier and order filter
        try:
            order = next((o for o in self._orders if (self._order_filter or (lambda x: True))(o) and getattr(o, 'Identifier', None) == getattr(self._only_order, 'Identifier', None)), None)
            return [order] if order is not None else []
        except Exception:
            return []

    # --- MountedSpaces override -----------------------------------------
    @property
    def MountedSpaces(self) -> "MountedSpaceList":
        # Build filtered list consistent with C# semantics
        try:
            backing = list(getattr(self, '_mounted_spaces', []) or [])
            if self._only_order is None and self._only_mounted_space is None:
                filtered = [m for m in backing if (getattr(m, 'Order', None) is None) or (m.Order in self.Orders)]
                return MountedSpaceList(filtered)

            if self._only_mounted_space is not None:
                filtered = [m for m in backing if m == self._only_mounted_space]
                return MountedSpaceList(filtered)

            # _only_order present
            filtered = [m for m in backing if ((m.Order in self.Orders) and getattr(m.Order, 'Identifier', None) == getattr(self._only_order, 'Identifier', None)) or getattr(m, 'Order', None) is None]
            return MountedSpaceList(filtered)
        except Exception:
            return MountedSpaceList(getattr(self, '_mounted_spaces', []) or [])

    @MountedSpaces.setter
    def MountedSpaces(self, value: Iterable[Any]):
        try:
            self._mounted_spaces = list(value) if value is not None else []
        except Exception:
            setattr(self, '_mounted_spaces', list(value) if value is not None else [])

    # --- Spaces override (complex logic) -------------------------------
    @property
    def Spaces(self) -> List[Any]:
        # If no _only_space and no _only_order, return base Spaces
        if getattr(self, '_only_space', None) is None and getattr(self, '_only_order', None) is None:
            return super().Spaces

        if getattr(self, '_only_space', None) is not None:
            # try to find matching space by Number and Side
            s = None
            try:
                for sp in list(getattr(self, '_spaces', []) or []):
                    if getattr(sp, 'Number', None) == getattr(self._only_space, 'Number', None) and getattr(getattr(sp, 'Side', getattr(sp, 'side', None)), 'upper', lambda: None)() == getattr(getattr(self._only_space, 'Side', getattr(self._only_space, 'side', None)), 'upper', lambda: None)():
                        s = sp
                        break
            except Exception:
                s = None
            return [s] if s is not None else []

        # _only_order present: compute quantityNeeded/previousSpaces similar to C#
        try:
            # previousOrdersSpaces: sum quantities for orders before first of current Orders in full _orders list
            first_current = next(iter(self.Orders), None)
            prev_count = 0
            if first_current is not None:
                try:
                    idx_first = list(self._orders).index(first_current)
                except Exception:
                    idx_first = 0
                prev_orders = list(self._orders)[:idx_first]
                for o in prev_orders:
                    prev_count += int(getattr(o, 'QuantityOfPalletsNeededRounded', getattr(o, 'QuantityOfPalletsNeeded', 0)) or 0) + int(getattr(o, 'AdditionalSpaces', 0) or 0)

            additional_spaces = sum(int(getattr(o, 'AdditionalSpaces', 0) or 0) for o in self.Orders)
            quantity_needed = sum(int(getattr(o, 'QuantityOfPalletsNeededRounded', getattr(o, 'QuantityOfPalletsNeeded', 0)) or 0) for o in self.Orders)

            # count mounted spaces associated to these orders
            base_mounted_spaces = [m for m in getattr(self, '_mounted_spaces', []) or []]
            order_mounted_spaces = sum(1 for m in base_mounted_spaces if getattr(m, 'Order', None) in self.Orders and getattr(m.Order, 'Identifier', None) == getattr(self._only_order, 'Identifier', None))

            quantity_expected = (quantity_needed + additional_spaces - order_mounted_spaces)
            quantity_of_spaces_needed = quantity_expected if quantity_expected <= len(getattr(self, '_spaces', []) or []) else len(getattr(self, '_spaces', []) or [])

            mounted_spaces_spaces = [m.Space for m in base_mounted_spaces]
            all_spaces = mounted_spaces_spaces + list(getattr(self, '_spaces', []) or [])
            # sort by Number
            try:
                all_spaces_sorted = sorted(all_spaces, key=lambda x: int(getattr(x, 'Number', getattr(x, 'number', 0)) or 0))
            except Exception:
                all_spaces_sorted = list(all_spaces)

            if self._skip_previous_order_spaces_quantity:
                try:
                    all_spaces_sorted = all_spaces_sorted[prev_count:]
                except Exception:
                    pass

            # exclude spaces that are present in mounted_spaces (i.e., already mounted)
            result = [s for s in all_spaces_sorted if s not in mounted_spaces_spaces]
            return result[:quantity_of_spaces_needed]
        except Exception:
            return super().Spaces

    @Spaces.setter
    def Spaces(self, value: Iterable[Any]):
        try:
            self._spaces = list(value) if value is not None else []
        except Exception:
            setattr(self, '_spaces', list(value) if value is not None else [])

    # --- Snapshot / From parity with C# --------------------------------
    def CreateSnapshot(self):
        # C#: _snapshot = From(this, Build)
        try:
            self._snapshot = deepcopy(self)
        except Exception:
            self._snapshot = self.CreateSnapshotMinimal()

    def ClearFilters(self):
        self._only_space = None
        self._only_mounted_space = None
        self._only_order = None
        self._order_filter = None
        return self
    
    def CreateSnapshot(self, *args, **kwargs):
        # support overload CreateSnapshot() and CreateSnapshot(space)
        if len(args) == 1:
            space = args[0]
            try:
                snap = deepcopy(self)
                snap.Spaces = [space]
                self._snapshot = snap
                return snap
            except Exception:
                snap = deepcopy(self)
                try:
                    snap.Spaces = [space]
                except Exception:
                    setattr(snap, '_spaces', [space])
                self._snapshot = snap
                return snap
        else:
            try:
                snap = deepcopy(self)
                self._snapshot = snap
                return snap
            except Exception:
                return self.CreateSnapshotMinimal()

    @staticmethod
    def From(context, builder: Callable[[str, List[Any], List[Any], Any], Any], space: Optional[Any] = None):
        # Port of C# From; builder should be a callable(number, orders, spaces, setting)
        only_order = getattr(context, '_only_order', None)
        only_space = getattr(context, '_only_space', None)
        only_mounted_space = getattr(context, '_only_mounted_space', None)
        order_filter = getattr(context, '_order_filter', None)

        # clear filters on source context (mimic C# behaviour)
        try:
            if hasattr(context, 'ClearFilters'):
                context.ClearFilters()
            if hasattr(context, 'ClearOrderFilters'):
                context.ClearOrderFilters()
        except Exception:
            pass

        # clone orders and spaces
        try:
            orders = [o.Clone() if hasattr(o, 'Clone') else deepcopy(o) for o in context.Orders]
        except Exception:
            orders = deepcopy(list(context.Orders))

        # spaces referenced by mounted spaces that are not in context.Spaces
        try:
            spaces_of_mounted = [m.Space for m in context.MountedSpaces if not any(getattr(y, 'Number', None) == getattr(m.Space, 'Number', None) and getattr(getattr(y, 'Side', getattr(y, 'side', None)), 'upper', lambda: None)() == getattr(getattr(m.Space, 'Side', getattr(m.Space, 'side', None)), 'upper', lambda: None)() for y in context.Spaces)]
        except Exception:
            spaces_of_mounted = []

        try:
            spaces = list(context.Spaces) + spaces_of_mounted
        except Exception:
            spaces = list(getattr(context, '_spaces', []) or []) + spaces_of_mounted

        if space is not None:
            spaces = [space]

        # attempt to call builder(number, orders, spaces, settings)
        try:
            new_ctx = builder(getattr(context, 'Number', None), orders, spaces, getattr(context, 'Settings', None))
        except Exception:
            # fallback: create a plain ASRuleContext
            new_ctx = ASRuleContext()
            new_ctx.Orders = orders
            new_ctx.Spaces = spaces

        # restore filters on new context
        try:
            if hasattr(new_ctx, 'WithOnlyOrder'):
                new_ctx.WithOnlyOrder(only_order)
            if hasattr(new_ctx, 'WithOnlySpace'):
                new_ctx.WithOnlySpace(only_space)
            if hasattr(new_ctx, 'WithOrderFilter') and order_filter is not None:
                new_ctx.WithOrderFilter(order_filter)
            if hasattr(new_ctx, 'SetSkipPreviousOrderSpacesQuantity'):
                new_ctx.SetSkipPreviousOrderSpacesQuantity(getattr(context, 'SkipPreviousOrderSpacesQuantity', getattr(context, '_skip_previous_order_spaces_quantity', True)))
        except Exception:
            pass

        # clone mounted spaces into new context when appropriate
        try:
            if space is None:
                for m in context.MountedSpaces:
                    if hasattr(m, 'Clone'):
                        try:
                            new_ctx.AddMountedSpace(m.Clone(orders, spaces))
                        except Exception:
                            try:
                                new_ctx.AddMountedSpace(deepcopy(m))
                            except Exception:
                                pass
                    else:
                        try:
                            new_ctx.AddMountedSpace(deepcopy(m))
                        except Exception:
                            pass
        except Exception:
            pass

        # restore source context filters
        try:
            if hasattr(context, 'WithOnlyOrder'):
                context.WithOnlyOrder(only_order)
            if hasattr(context, 'WithOnlySpace'):
                context.WithOnlySpace(only_space)
            if hasattr(context, 'WithOnlyMountedSpace'):
                context.WithOnlyMountedSpace(only_mounted_space)
            if hasattr(context, 'WithOrderFilter') and order_filter is not None:
                context.WithOrderFilter(order_filter)
        except Exception:
            pass

        return new_ctx


class MixedRuleContext(ASRuleContext):
    """Minor variant used by mixed rules - kept for parity with C#."""
    def __init__(self, json_path: Optional[Union[str, Path]] = None, config_path: Optional[Union[str, Path]] = None, *args, **kwargs):
        super().__init__(json_path=json_path, config_path=config_path, *args, **kwargs)
        self._kind = "Mixed"

class T4RuleContext(ASRuleContext):
    """Minor variant used by T4 rules - kept for parity with C#."""
    def __init__(self, json_path: Optional[Union[str, Path]] = None, config_path: Optional[Union[str, Path]] = None, *args, **kwargs):
        super().__init__(json_path=json_path, config_path=config_path, *args, **kwargs)
        self._kind = "T4"


class CrossDockingRuleContext(ASRuleContext):
    """
    Port of C# CrossDockingRuleContext : extends ASRuleContext and provides
    CrossDocking-specific builder and helpers. Implements:
      - static Build(number, orders, spaces, setting)
      - CreateSnapshot() and CreateSnapshot(space)
      - RemoveMountedSpace(mounted_space)

    This mirrors the small, explicit behavior in the C# class used by rules.
    """
    def __init__(self, json_path: Optional[Union[str, Path]] = None, config_path: Optional[Union[str, Path]] = None, *args, **kwargs):
        super().__init__(json_path=json_path, config_path=config_path, *args, **kwargs)
        self._kind = "CrossDocking"

    @staticmethod
    def Build(number: str, orders: Iterable[Any], spaces: Iterable[Any], setting: Any) -> "CrossDockingRuleContext":
        ctx = CrossDockingRuleContext()
        # set basic fields like the C# builder
        ctx.Number = number
        try:
            ctx._orders = list(orders) if orders is not None else []
        except Exception:
            setattr(ctx, "_orders", list(orders) if orders is not None else [])

        try:
            ctx._spaces = list(spaces) if spaces is not None else []
        except Exception:
            setattr(ctx, "_spaces", list(spaces) if spaces is not None else [])

        # store setting object
        setattr(ctx, "_setting", setting)

        # CrossDocking explicitly disables skipping previous order spaces quantity
        ctx.SetSkipPreviousOrderSpacesQuantity(0)

        return ctx

    # def Create2Snapshot(self, space: Optional[Any] = None) -> "CrossDockingRuleContext":
    #     """
    #     Create a snapshot of the context. If `space` is provided, the snapshot's Spaces
    #     will be limited to that single space (parity with the C# overload CreateSnapshot(ISpace)).
    #     The snapshot is stored on `self._snapshot` where possible to mimic C# behaviour.
    #     """
    #     try:
    #         snap = deepcopy(self)
    #         if space is not None:
    #             try:
    #                 snap.Spaces = [space]
    #             except Exception:
    #                 setattr(snap, "_spaces", [space])
    #         # store snapshot for parity with C# usage
    #         try:
    #             self._snapshot = snap
    #         except Exception:
    #             pass
    #         return snap
    #     except Exception:
    #         # best-effort fallback
    #         snap = deepcopy(self)
    #         if space is not None:
    #             try:
    #                 snap.Spaces = [space]
    #             except Exception:
    #                 setattr(snap, "_spaces", [space])
    #         return snap

    # snake_case / Python-friendly aliases -------------------------------------------------
    @staticmethod
    def build(number: str, orders: Iterable[Any], spaces: Iterable[Any], setting: Any) -> "CrossDockingRuleContext":
        """Alias for Build (snake_case compatibility)."""
        return CrossDockingRuleContext.Build(number, orders, spaces, setting)

    @staticmethod
    def from_(context: Any, orders: Iterable[Any], spaces: Iterable[Any], mounted_spaces: Iterable[Any]) -> "CrossDockingRuleContext":
        """Alias to mimic Context.From-style usage when a caller expects a 'from_' helper.

        This will attempt to call the module-level From if available, otherwise perform a
        conservative deepcopy and assign collections.
        """
        try:
            # try to reuse the generic From implementation if present
            return globals().get("CrossDockingRuleContext", CrossDockingRuleContext).From(context, orders, spaces, mounted_spaces)
        except Exception:
            snap = deepcopy(context)
            try:
                snap.Orders = list(orders)
                snap.Spaces = list(spaces)
                snap.MountedSpaces = list(mounted_spaces)
            except Exception:
                setattr(snap, "_orders", list(orders))
                setattr(snap, "_spaces", list(spaces))
                setattr(snap, "_mounted_spaces", list(mounted_spaces))
            return snap

    def create_snapshot(self, space: Optional[Any] = None) -> "CrossDockingRuleContext":
        """snake_case alias for CreateSnapshot(space)."""
        return self.CreateSnapshot(space)

    def RemoveMountedSpace(self, mounted_space: Any):
        """Remove a mounted space and re-add its underlying Space to the available Spaces list.

        Mirrors C# RemoveMountedSpace which does:
            _spaces.Add(mountedSpace.Space);
            _mountedSpaces.Remove(mountedSpace);
        """
        # add space back to spaces list if not present
        try:
            space = getattr(mounted_space, "Space", None)
            if space is not None:
                if not any(getattr(s, "Number", None) == getattr(space, "Number", None) for s in self._spaces):
                    self._spaces.append(space)
        except Exception:
            pass

        # remove mounted space from mounted spaces
        try:
            if mounted_space in self._mounted_spaces:
                self._mounted_spaces.remove(mounted_space)
        except Exception:
            # fallback: try to filter by id
            try:
                mid = getattr(mounted_space, "MountedSpaceId", getattr(mounted_space, "Id", None))
                self._mounted_spaces = [m for m in getattr(self, "_mounted_spaces", []) if getattr(m, "MountedSpaceId", getattr(m, "Id", None)) != mid]
            except Exception:
                pass

    def remove_mounted_space(self, mounted_space: Any):
        return self.RemoveMountedSpace(mounted_space)
    
