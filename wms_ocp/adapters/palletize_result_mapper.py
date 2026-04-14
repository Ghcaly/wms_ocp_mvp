from typing import Any, Dict, List, Optional
import json
import datetime
import logging
# from ..domain.itemList import ItemList

class PalletizeResultMapper:
    """Map a runtime `Context` to the canonical PalletizeResultEvent (camelCase).

    The mapper reads `context.mounted_spaces` (or `context.MountedSpaces`) and
    extracts pallets, items and metadata to produce a dict that matches the
    output.json produced by the original C# adapter.
    """

    @staticmethod
    def _side_to_initial(side_raw: Optional[Any]) -> str:
        if side_raw is None:
            return "H"
        if isinstance(side_raw, (bytes, bytearray)):
            try:
                side_raw = side_raw.decode('utf-8')
            except Exception:
                side_raw = str(side_raw)
        ch = None
        if isinstance(side_raw, int):
            try:
                ch = chr(side_raw).upper()
            except Exception:
                ch = str(side_raw).upper()
        else:
            s = str(side_raw).strip()
            if s.isdigit():
                try:
                    ch = chr(int(s)).upper()
                except Exception:
                    ch = s.upper()
            else:
                ch = s.upper()
        if ch in ("M", "DRIVER", "D", "MOTORISTA", "MOTOR"):
            return "M"
        return "H"

    @staticmethod
    def _map_side(side_raw: Optional[Any]) -> str:
        init = PalletizeResultMapper._side_to_initial(side_raw)
        return "Driver" if init == "M" else "Helper"

    def _build_pallet_code(self, pallet, ordinal, total_bays, context=None):
        raw_side = getattr(pallet, "Side", None)
        if raw_side is None and getattr(pallet, "Space", None) is not None:
            raw_side = getattr(pallet.Space, "Side", None)
        side_initial = self._side_to_initial(raw_side)
        bay_number = int(getattr(pallet, "Number", 0) or 0)
        total = int(total_bays or getattr(context, "TotalBays", 0) or 0)
        return f"P{bay_number:02}_{side_initial}_{ordinal}/{total}"

    @staticmethod
    def _to_iso(o: Any):
        if isinstance(o, (datetime.datetime, datetime.date)):
            return o.isoformat()
        return o

    @classmethod
    def build_item(cls, mp: Any) -> Dict[str, Any]:
        # unify product access
        product_obj = getattr(mp, 'Product', None) or getattr(mp, 'product', None) or (mp.get('Product') if isinstance(mp, dict) else None)

        desc = getattr(mp, 'Description', None) or getattr(mp, 'description', None) or (getattr(product_obj, 'Name', None) if product_obj is not None else None) or (product_obj.get('name') if isinstance(product_obj, dict) else None)
        code = (getattr(product_obj, 'Code', None) if product_obj is not None else None) or (product_obj.get('Code') if isinstance(product_obj, dict) else None) or getattr(mp, 'cdItem', None) or getattr(mp, 'code', None) or (mp.get('code') if isinstance(mp, dict) else None)

        qty = getattr(mp, 'Amount', None) or getattr(mp, 'amount', None) or getattr(mp, 'qtUnVenda', None) or (mp.get('Amount') if isinstance(mp, dict) else None) or 0
        try:
            qty = int(qty) if qty is not None else 0
        except Exception:
            qty = 0

        occ = getattr(mp, 'Occupation', None) or getattr(mp, 'occupation', None) or getattr(mp, 'PercentOccupationIntoDefaultPalletSize', None) or (mp.get('Occupation') if isinstance(mp, dict) else None)
        asm = getattr(mp, 'AssemblySequence', None) or getattr(mp, 'assembly_sequence', None) or getattr(mp, 'sqMontagem', None) or (mp.get('AssemblySequence') if isinstance(mp, dict) else None)

        delivery = None
        try:
            delivery = getattr(getattr(mp, 'Item', None), 'DeliveryOrder', None) or getattr(getattr(mp, 'Item', None), '_delivery_orders', None)
        except Exception:
            delivery = None

        map_number = getattr(mp, 'MapNumber', None) or getattr(mp, 'map_number', None) or (getattr(getattr(mp, 'Order', None), 'MapNumber', None) if getattr(mp, 'Order', None) else None) or (mp.get('MapNumber') if isinstance(mp, dict) else None)

        gross = None
        if product_obj is not None:
            gross = getattr(product_obj, 'GrossWeight', None) or (product_obj.get('GrossWeight') if isinstance(product_obj, dict) else None)

        total_weight = getattr(mp, 'TotalWeight', None) or getattr(mp, 'total_weight', None) or None
        if total_weight is None and gross is not None:
            try:
                total_weight = float(gross) * qty
            except Exception:
                total_weight = None

        packing = getattr(product_obj, 'PackingGroup', None) or (product_obj.get('PackingGroup') if isinstance(product_obj, dict) else None) or getattr(product_obj, 'packing', None) or {}
        packing_obj = {
            'Code': packing.get('PackingCode') if isinstance(packing, dict) else getattr(packing, 'PackingCode', None),
            'Group': packing.get('GroupCode') if isinstance(packing, dict) else getattr(packing, 'GroupCode', None),
            'SubGroup': packing.get('SubGroupCode') if isinstance(packing, dict) else getattr(packing, 'SubGroupCode', None),
        }

        order_obj = getattr(mp, 'Order', None) or getattr(mp, 'order', None) or (mp.get('Order') if isinstance(mp, dict) else None)
        customer = next(iter(mp.Item.ClientQuantity)) or None if getattr(mp, 'Item', None) is not None else None
        if order_obj is not None and customer is None:
            items_list = getattr(order_obj, 'Items', None) or getattr(order_obj, 'items', None) or (order_obj.get('Items') if isinstance(order_obj, dict) else None) or []
            first_item = None
            if items_list:
                try:
                    first_item = items_list[0]
                except Exception:
                    for it in items_list:
                        first_item = it
                        break
            if first_item is not None:
                customer = getattr(first_item, 'Customer', None) or getattr(first_item, 'customer', None) or (first_item.get('Customer') if isinstance(first_item, dict) else None)

        # Detect BoxCode if present (expanded BoxTemplate child will set this)
        box_code = None
        if isinstance(mp, dict):
            box_code = mp.get('BoxCode') or mp.get('box_code') or (mp.get('Product') or {}).get('BoxCode') if mp.get('Product') else None
            if box_code is None and mp.get('Product'):
                try:
                    box_code = (mp.get('Product') or {}).get('CodigoCaixa') or (mp.get('Product') or {}).get('codigo_caixa')
                except Exception:
                    box_code = None
        else:
            box_code = getattr(mp, 'BoxCode', None) or getattr(mp, 'box_code', None)
            if box_code is None and product_obj is not None:
                box_code = getattr(product_obj, 'BoxCode', None) or getattr(product_obj, 'CodigoCaixa', None) or getattr(product_obj, 'codigo_caixa', None)

        # Marketplace field: if box_code present expose object with BoxCode, else keep legacy boolean/flag
        marketplace_field = None
        if box_code is not None:
            try:
                marketplace_field = {'BoxCode': str(box_code)}
            except Exception:
                marketplace_field = {'BoxCode': box_code}
        else:
            is_mkt = False
            try:
                is_mkt_candidate = getattr(mp, 'IsMarketplace', None)
                if callable(is_mkt_candidate):
                    is_mkt = bool(is_mkt_candidate())
                elif is_mkt_candidate is not None:
                    is_mkt = bool(is_mkt_candidate)
                else:
                    if isinstance(mp, dict):
                        is_mkt = bool(mp.get('Marketplace') or mp.get('marketplace') or False)
                    else:
                        is_mkt = bool(getattr(mp, 'IsMarketplace', getattr(mp, 'Marketplace', False)))
            except Exception:
                is_mkt = False
            marketplace_field = is_mkt

        return {
            'Description': desc,
            'Code': str(code) if code is not None else None,
            'Quantity': qty,
            'AclQtdUom': None,
            'DetachedQuantity': None,
            'RemainingQuantity': None,
            'Occupation': float(occ) if occ is not None else None,
            'AssemblySequence': asm,
            'DeliverySequence': delivery,
            'MapNumber': map_number,
            'GrossWeight': float(gross) if gross is not None else None,
            'TotalWeight': total_weight,
            'LayerCode': getattr(product_obj, 'LayerCode', None) if product_obj is not None else None,
            'LayerQuantity': None,
            'IsTopOfPallet': (mp.IsTopOfPallet() if callable(getattr(mp, 'IsTopOfPallet', None)) else False),
            'IsChopp': (mp.IsChopp() if callable(getattr(mp, 'IsChopp', None)) else False),
            'IsReturnable': (mp.IsReturnable() if callable(getattr(mp, 'IsReturnable', None)) else False),
            'IsIsotonicWater': (mp.IsIsotonicWater() if callable(getattr(mp, 'IsIsotonicWater', None)) else False),
            'Marketplace': marketplace_field,
            'Packing': packing_obj,
            'Segregated': None,
            'Realocated': getattr(mp, 'Realocated', False),
            'AdditionalOccupation': float(getattr(mp, 'AdditionalOccupation', None)) if getattr(mp, 'AdditionalOccupation', None) is not None else None,
            'PrePickingTypeCorrelationId': None,
            'ItemCorrelationId': getattr(mp, 'ItemCorrelationId', None) or getattr(mp, 'item_correlation_id', None) or getattr(mp, 'WmsId', None) or (mp.get('ItemCorrelationId') if isinstance(mp, dict) else None),
            'Customer': customer,
        }

    @classmethod
    def build_pallet(cls, ms: Any, context: Any = None) -> Dict[str, Any]:
        from types import SimpleNamespace
        import pandas as pd
        from pathlib import Path
        from ..adapters.database import fill_item_from_row, buscar_item
        from ..domain.item import Item as DomainItem

        space = getattr(ms, 'Space', None) or getattr(ms, 'space', None)
        number = getattr(space, 'Number', None) or getattr(space, 'number', None) or getattr(ms, 'Number', None) or getattr(ms, 'number', None)
        side_raw = getattr(space, 'Side', None) or getattr(space, 'side', None) or getattr(ms, 'Side', None) or getattr(ms, 'side', None)
        side = cls._map_side(side_raw)
        size = getattr(space, 'Size', None) or getattr(space, 'size', None)
        occupation = getattr(ms, 'Occupation', None) or getattr(ms, 'occupation', None)
        weight = getattr(ms, 'Weight', None) or getattr(ms, 'weight', None)
        is_closed = getattr(ms, 'IsClosed', None) or getattr(ms, 'is_closed', None) or False
        is_palletized = True

        # build code if absent
        code = getattr(ms, 'Code', None) or getattr(ms, 'code', None)
        if not code:
            try:
                n = int(number) if number is not None else 0
            except Exception:
                n = 0
            try:
                raw_initial = cls._side_to_initial(side_raw)
            except Exception:
                raw_initial = 'H'
            code_initial = 'A' if raw_initial == 'H' else 'M'
            size_part = str(size) if size is not None else '0'
            code = f"P{n:02d}_{code_initial}_{n:02d}_1/{size_part}"

        # collect items from containers or Products
        items_src = []
        containers = getattr(ms, 'Containers', None) or getattr(ms, 'containers', None) or None
        if containers:
            for c in containers:
                prods = None
                for cand in ('GetProducts', 'Products', 'products'):
                    try:
                        if hasattr(c, cand):
                            val = getattr(c, cand)
                            prods = val() if callable(val) else val
                            break
                    except Exception:
                        prods = None
                if prods:
                    items_src.extend(list(prods))
        else:
            try:
                if hasattr(ms, 'GetProducts'):
                    items_src = list(ms.GetProducts() or [])
                else:
                    items_src = list(getattr(ms, 'Products', []) or [])
            except Exception:
                items_src = []

        # helper: try to find product metadata in context (orders/products)
        def _find_product_in_context(search_code):
            if not search_code or context is None:
                return None
            try:
                prods = getattr(context, 'products', None) or getattr(context, 'Produtos', None) or []
                for p in prods or []:
                    try:
                        if str(getattr(p, 'Code', None)) == str(search_code):
                            return p
                    except Exception:
                        continue
            except Exception:
                pass
            try:
                orders = getattr(context, 'Orders', None) or getattr(context, 'orders', None) or []
                for o in orders or []:
                    items = getattr(o, 'Items', None) or getattr(o, 'items', None) or []
                    for it in items or []:
                        prod = getattr(it, 'Product', None) or getattr(it, 'product', None)
                        if prod is not None:
                            try:
                                if str(getattr(prod, 'Code', None)) == str(search_code):
                                    return prod
                            except Exception:
                                continue
            except Exception:
                pass
            return None

        # helper: try to enrich product from CSV (same CSV used earlier)
        def _enrich_product_from_csv(search_code):
            try:
                base_data = Path(__file__).parent.parent / 'database'
                candidate_files = [
                    base_data / "csv-itens-19012026.csv"
                ]
                df = None
                for fpath in candidate_files:
                    try:
                        if fpath.exists():
                            df = pd.read_csv(fpath, sep=';')
                            break
                    except Exception:
                        continue
                if df is None:
                    return None
                df = df.where(pd.notnull(df), None).astype(object)
                df['Código'] = df['Código'].astype(str)
                df['Código Unb'] = df['Código Unb'].astype(str)
                df = df[df['Id Catálogo']==2].set_index("Código")
                key = str(search_code)
                if key not in df.index:
                    return None
                row = buscar_item(df[df['Id Catálogo']==2], key)
                temp_item = DomainItem(Code=key, Amount=0)
                try:
                    enriched = fill_item_from_row(temp_item, [], None, row)
                    return enriched.Product if enriched and getattr(enriched, 'Product', None) else None
                except Exception:
                    return getattr(temp_item, 'Product', None)
            except Exception as e:
                print(f"Erro ao enriquecer produto do CSV para código {search_code}: {e}")
                return None

        # Expand BoxTemplate-mounted-products into child SKU items, enriching metadata
        items_out: List[Dict[str, Any]] = []
        for mp in items_src:
            prod = getattr(mp, 'Product', None) or getattr(mp, 'product', None)
            items_in_box = None
            try:
                items_in_box = getattr(prod, 'ItemsInBox', None) or getattr(mp, 'items_in_box', None) or getattr(prod, 'items_in_box', None)
            except Exception:
                items_in_box = None

            if items_in_box:
                for child in items_in_box:
                    try:
                        child_code = getattr(child, 'ItemCode', None) or getattr(child, 'item_code', None) or getattr(child, 'code', None)
                        # compute qty from DeliveryOrders if present
                        qty = 0
                        delivery_orders = getattr(child, 'DeliveryOrders', None) or getattr(child, 'DeliveryOrders', []) or []
                        if delivery_orders:
                            for do in delivery_orders:
                                try:
                                    qty += int(getattr(do, 'Amount', 0) or 0)
                                except Exception:
                                    try:
                                        qty += int(float(getattr(do, 'Amount', 0) or 0))
                                    except Exception:
                                        pass
                        else:
                            qty = int(getattr(child, 'Amount', None) or getattr(child, 'amount', 0) or 0)

                        # try to find richer product metadata in context
                        product_obj = _find_product_in_context(child_code)
                        if product_obj is None:
                            product_obj = _enrich_product_from_csv(child_code)

                        mp_child = SimpleNamespace()
                        if product_obj:
                            mp_child.Product = product_obj
                        else:
                            # fallback placeholder product (will be partially filled)
                            mp_child.Product = SimpleNamespace(
                                Code=child_code,
                                Name=getattr(child, 'Name', None) or getattr(child, 'name', None),
                                CodePromax=getattr(child, 'CodePromax', None),
                                LayerCode=getattr(child, 'LayerCode', 0) or 0,
                                GrossWeight=getattr(child, 'Gross_weight', None) or getattr(child, 'GrossWeight', None) or None,
                                PackingGroup=getattr(child, 'PackingGroup', None) or {},
                                PalletSetting=SimpleNamespace(IncludeTopOfPallet=False),
                            )
                            setattr(mp_child.Product, 'IsTopOfPallet', lambda: False)
                            setattr(mp_child.Product, 'IsChopp', lambda: False)
                            setattr(mp_child.Product, 'IsReturnable', lambda: False)
                            setattr(mp_child.Product, 'IsIsotonicWater', lambda: False)

                        mp_child.Amount = qty
                        mp_child.amount = qty
                        mp_child.AmountRemaining = qty
                        mp_child.TotalWeight = (getattr(mp_child.Product, 'GrossWeight', None) or 0)
                        mp_child.Order = getattr(mp, 'Order', getattr(mp, 'order', None))
                        mp_child.AssemblySequence = getattr(mp, 'AssemblySequence', getattr(mp, 'assembly_sequence', None))

                        # --- NEW: take occupation from box-template (parent mp / prod) ---
                        box_occ = None
                        box_occ = getattr(mp, 'Occupation', None) or getattr(prod, 'Occupation', None) or getattr(mp, 'PercentOccupationIntoDefaultPalletSize', None) or getattr(prod, 'PercentOccupationIntoDefaultPalletSize', None)
                        if box_occ is not None:
                            try:
                                occ_val = float(box_occ)
                            except Exception:
                                occ_val = box_occ
                            mp_child.Occupation = occ_val
                            mp_child.occupation = occ_val
                        # --- end NEW ---

                        try:
                            box_code_val = getattr(prod, 'Code', None)
                        except Exception:
                            box_code_val = getattr(prod, 'code', None) if prod is not None else None
                        mp_child.BoxCode = box_code_val
                        mp_child.IsTopOfPallet = lambda _mp=mp_child: getattr(_mp.Product, 'IsTopOfPallet', lambda: False)()
                        mp_child.IsChopp = lambda _mp=mp_child: getattr(_mp.Product, 'IsChopp', lambda: False)()
                        mp_child.IsReturnable = lambda _mp=mp_child: getattr(_mp.Product, 'IsReturnable', lambda: False)()
                        mp_child.IsIsotonicWater = lambda _mp=mp_child: getattr(_mp.Product, 'IsIsotonicWater', lambda: False)()
                        mp_child.IsMarketplace = lambda: False
                        mp_child.Realocated = getattr(mp, 'Realocated', False)
                        mp_child.AdditionalOccupation = getattr(mp, 'AdditionalOccupation', 0)
                        mp_child.ItemCorrelationId = getattr(mp, 'ItemCorrelationId', None)

                        items_out.append(cls.build_item(mp_child))
                    except Exception:
                        continue
                # skip adding box-template itself
                continue

            # Non-boxed flow: use original mounted-product
            try:
                items_out.append(cls.build_item(mp))
            except Exception:
                continue

        # Sort items by assemblySequence ascending (missing or non-numeric values go last)
        def _asm_key(it: Dict[str, Any]):
            v = it.get('AssemblySequence')
            if v is None:
                return float('inf')
            try:
                return int(v)
            except Exception:
                try:
                    return int(float(str(v)))
                except Exception:
                    return float('inf')

        items_out = sorted(items_out, key=_asm_key)

        # roadShowOrder: collect delivery orders from items
        road_orders = []
        # for it in items_out:
        #     ds = it.get('DeliverySequence')
        #     if ds is not None:
        #         ds_s = str(ds)
        #         if ds_s not in road_orders:
        #             road_orders.append(ds_s)
        for it in items_out:
            ds = it.get('DeliverySequence', {})
            if ds is not None:
                for k in ds:
                    k_s = str(k)
                    if k_s not in road_orders:
                        road_orders.append(k_s)
        road_show = "|".join(road_orders) if road_orders else None

        # customer: prefer mounted_space.Order.Customer / ms.Customer ; if empty, infer from first item
        customer = getattr(ms, 'Customer', None) or getattr(getattr(ms, 'Order', None), 'Customer', None)
        if not customer:
            for it in items_out:
                c = it.get('Customer') or it.get('customer')
                if c:
                    customer = c
                    break

        # license plates/document numbers extraction
        license_plates = getattr(ms, 'LicensePlates', None) or getattr(ms, 'license_plates', None) or []
        document_numbers = []
        for it in items_out:
            mn = it.get('MapNumber') or it.get('mapNumber')
            if mn is not None:
                if isinstance(mn, (list, tuple)):
                    document_numbers.extend([str(x) for x in mn if x])
                else:
                    document_numbers.append(str(mn))
        document_numbers = list(dict.fromkeys([d for d in document_numbers if d]))

        # Compute pallet weight from expanded items (BoxTemplate containers excluded, contents included).
        # Mirrors legado: the Peso shown in the report is the sum of content item weights, not the
        # physical box weights (which are only used internally for SideBalance weight balancing).
        content_weight = sum(
            float(it.get('GrossWeight') or 0) * int(it.get('Quantity') or 0)
            for it in items_out
            if it.get('GrossWeight') is not None
        )
        report_weight = content_weight if content_weight > 0 else (float(weight) if weight is not None else None)

        return {
            'Number': number,
            'Code': code,
            'RoadShowOrder': road_show,
            'Customer': customer,
            'Layer': getattr(ms, 'Layer', getattr(ms, 'layer', False)),
            'Side': side,
            'Size': float(size) if size is not None else None,
            'Occupation': float(occupation) if occupation is not None else None,
            'Weight': report_weight,
            'IsClosed': is_closed,
            'IsPalletized': is_palletized,
            'Items': items_out,
            'LoadTypeOnPallet': getattr(ms, 'LoadTypeOnPallet', getattr(ms, 'load_type_on_pallet', None)) or 'Normal',
            'LicensePlates': license_plates,
            'DocumentNumbers': document_numbers,
        }

    @classmethod
    def build_event(cls, context: Any, palletize_dto: Optional[Any] = None, request: Optional[Any] = None, success: bool = True, message: Optional[str] = None) -> Dict[str, Any]:
        pallets_out: List[Dict[str, Any]] = []

        mspaces = None
        if hasattr(context, 'mounted_spaces'):
            mspaces = getattr(context, 'mounted_spaces') or []
        elif hasattr(context, 'MountedSpaces'):
            ms = getattr(context, 'MountedSpaces')
            try:
                mspaces = ms.to_list() if hasattr(ms, 'to_list') else list(ms)
            except Exception:
                try:
                    mspaces = list(ms)
                except Exception:
                    mspaces = []
        else:
            mspaces = []

        for ms in mspaces:
            try:
                pallets_out.append(cls.build_pallet(ms, context=context))
            except Exception as e:
                print(f"Erro ao mapear pallet no PalletizeResultMapper: {e}")
                continue
        try:
            cls.build_pallets_empty(context, pallets_out)
        except Exception:
            pass

        not_palet = []
        np_items = context.GetItemsWithAmountRemaining()
        for p in np_items:
            code = p.Code
            qty = p.Amount
            desc = p.Product.Name

            packing = getattr(p.Product, 'PackingGroup', None) or getattr(p.Product, 'packing', None) or {}
            packing_obj = {
                'Code': packing.get('PackingCode') if isinstance(packing, dict) else getattr(packing, 'PackingCode', None),
                'Group': packing.get('GroupCode') if isinstance(packing, dict) else getattr(packing, 'GroupCode', None),
                'SubGroup': packing.get('SubGroupCode') if isinstance(packing, dict) else getattr(packing, 'SubGroupCode', None),
            }

            gross = getattr(p.Product, 'GrossWeight', None)
            total_weight = float(gross) * qty if gross is not None else None

            occ = getattr(p, 'Occupation', None) or getattr(p, 'occupation', None) or getattr(p, 'PercentOccupationIntoDefaultPalletSize', None) or None

            not_palet.append({
                'Quantity': qty,
                'Code': str(code) if code is not None else None,
                'Description': desc if desc is not None else None,
                'GrossWeight': float(gross) if gross is not None else None,
                'TotalWeight': total_weight,
                'Occupation': float(occ) if occ is not None else None,
                'Packing': packing_obj,
                'IsTopOfPallet': p.Product.PalletSetting.IncludeTopOfPallet,
                'IsChopp': p.Product.IsChopp(),
                'IsReturnable': p.Product.IsReturnable(),
                'IsIsotonicWater': p.Product.IsIsotonicWater(),
            })

        pallets_out.append({'Code': 'Z_ITEM_NAO_PALLETIZADO', 'IsClosed': False, 'IsPalletized': False, 'Items': not_palet})

        def _pallet_sort_key(p: dict):
            num = p.get('Number')
            try:
                n = int(num) if num is not None else float('inf')
            except Exception:
                try:
                    n = int(str(num))
                except Exception:
                    n = float('inf')
            code = p.get('Code') or ''
            return (n, str(code))

        try:
            pallets_out = sorted(pallets_out, key=_pallet_sort_key)
        except Exception:
            pass

        result = {'success': bool(success), 'message': message, 'status': 'Success' if success else 'GenericError' }

        event = {
            'UnbCode': palletize_dto.unb_code,
            'VehiclePlate': palletize_dto.vehicle_plate,
            'DocumentNumber': palletize_dto.document_number,
            'DocumentType': palletize_dto.document_type,
            'DeliveryDate': palletize_dto.delivery_date,
            'Pallets': pallets_out,
            'Request': palletize_dto.request,
            'Result': result,
            'UniqueKey': palletize_dto.unique_key,
            'CatalogName': palletize_dto.catalog_name,
        }

        def _fill_missing(obj: Any):
            if isinstance(obj, dict):
                for k, v in list(obj.items()):
                    if v is None:
                        obj[k] = None
                    else:
                        _fill_missing(v)
            elif isinstance(obj, list):
                for i in range(len(obj)):
                    if obj[i] is None:
                        obj[i] = None
                    else:
                        _fill_missing(obj[i])

        def _sanitize(o: Any, _seen: set = None):
            if _seen is None:
                _seen = set()
            oid = id(o)
            if oid in _seen:
                return str(o)
            if isinstance(o, (dict, list)):
                _seen.add(oid)

            if isinstance(o, dict):
                out = {}
                for k, v in o.items():
                    out[str(k)] = _sanitize(v, _seen)
                return out
            if isinstance(o, list):
                return [_sanitize(v, _seen) for v in o]
            if isinstance(o, (str, int, float, bool)) or o is None:
                return o
            if isinstance(o, (datetime.date, datetime.datetime)):
                return cls._to_iso(o)
            try:
                if hasattr(o, 'to_dict') and callable(getattr(o, 'to_dict')):
                    return _sanitize(o.to_dict(), _seen)
                if hasattr(o, 'to_json') and callable(getattr(o, 'to_json')):
                    return _sanitize(o.to_json(), _seen)
            except Exception:
                pass
            try:
                return str(o)
            except Exception:
                return None

        event = _sanitize(event)
        _fill_missing(event)
        return event

    @classmethod
    def build_pallets_empty(cls, context: Any, pallets_out: List[Dict[str, Any]]) -> None:
        def _normalize_key(num, side_raw):
            try:
                n = int(num) if num is not None else None
            except Exception:
                try:
                    n = int(str(num))
                except Exception:
                    n = None
            init = cls._side_to_initial(side_raw)
            return (n, init)

        existing_keys = set()
        for p in pallets_out:
            try:
                existing_keys.add(_normalize_key(p.get('Number') or p.get('number'), p.get('Side') or p.get('side')))
            except Exception:
                continue

        try:
            if hasattr(context, 'GetAllSpaces'):
                spaces = context.GetAllSpaces() or []
            elif hasattr(context, 'get_all_spaces'):
                spaces = context.get_all_spaces() or []
            else:
                spaces = getattr(context, 'spaces', []) or []
        except Exception:
            spaces = getattr(context, 'spaces', []) or []

        for sp in spaces or []:
            try:
                sp_num = getattr(sp, 'Number', None) or getattr(sp, 'number', None)
                sp_side_raw = getattr(sp, 'Side', None) or getattr(sp, 'side', None)
                sp_size = getattr(sp, 'Size', None) or getattr(sp, 'size', None)
                key = _normalize_key(sp_num, sp_side_raw)
                if key in existing_keys:
                    continue

                try:
                    n = int(sp_num) if sp_num is not None else 0
                except Exception:
                    try:
                        n = int(str(sp_num))
                    except Exception:
                        n = 0
                raw_initial = cls._side_to_initial(sp_side_raw)
                code_initial = 'A' if raw_initial == 'H' else 'M'
                size_part = str(sp_size) if sp_size is not None else '0'
                code = f"P{n:02d}_{code_initial}_{n:02d}_1/{size_part}"

                pallet_empty = {
                    'Number': sp_num,
                    'Code': code,
                    'RoadShowOrder': None,
                    'Customer': None,
                    'Layer': False,
                    'Side': cls._map_side(sp_side_raw),
                    'Size': sp_size,
                    'Occupation': 0,
                    'Weight': 0,
                    'IsClosed': False,
                    'IsPalletized': True,
                    'Items': [],
                    'LoadTypeOnPallet': getattr(sp, 'LoadTypeOnPallet', getattr(sp, 'load_type_on_pallet', None)) or 'Normal',
                    'LicensePlates': None,
                    'DocumentNumbers': [],
                }
                pallets_out.append(pallet_empty)
                existing_keys.add(key)
            except Exception:
                continue

    @classmethod
    def save(cls, context: Any, output_path: str, indent: int = 2) -> None:
        try:
            counts = cls._count_items_for_event(context)
            logger = logging.getLogger(__name__)
            logger.info("PalletizeResultMapper: items summary before build_event:")
            logger.info(f"  MountedSpaces: {counts.get('mounted_spaces', 0)}")
            logger.info(f"  Total items (sum quantities): {counts.get('total_quantity', 0)}")
            logger.info(f"  Distinct SKUs: {counts.get('distinct_codes', 0)}")
            top = counts.get('top_codes', [])
            if top:
                logger.info("  Top codes (qty): " + ", ".join([f"{c}:{q}" for c, q in top]))
        except Exception as e:
            try:
                print(f"Erro ao contar itens antes do build_event: {e}")
            except Exception:
                pass

        event = cls.build_event(context, palletize_dto=context.palletize_dto, request=context.palletize_dto.request)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(event, f, ensure_ascii=False, indent=indent, default=cls._to_iso)

    @classmethod
    def _count_items_for_event(cls, context: Any) -> Dict[str, Any]:
        mounted_count = 0
        code_counts: Dict[str, int] = {}
        total_quantity = 0

        mspaces = None
        if hasattr(context, 'mounted_spaces'):
            mspaces = getattr(context, 'mounted_spaces') or []
        elif hasattr(context, 'MountedSpaces'):
            ms = getattr(context, 'MountedSpaces')
            try:
                mspaces = ms.to_list() if hasattr(ms, 'to_list') else list(ms)
            except Exception:
                try:
                    mspaces = list(ms)
                except Exception:
                    mspaces = []
        else:
            mspaces = []

        for ms in mspaces:
            try:
                mounted_count += 1
                pal = cls.build_pallet(ms, context=context)
                items = pal.get('Items') or pal.get('items', []) or []
                for it in items:
                    code = it.get('Code') or it.get('code') if isinstance(it, dict) else None
                    qty = it.get('Quantity') or it.get('quantity') if isinstance(it, dict) else None
                    try:
                        qn = int(qty) if qty is not None else 0
                    except Exception:
                        try:
                            qn = int(float(qty))
                        except Exception:
                            qn = 0
                    total_quantity += qn
                    if code:
                        code_counts[code] = code_counts.get(code, 0) + qn
            except Exception:
                continue

        distinct_codes = len(code_counts)
        top_codes = sorted(code_counts.items(), key=lambda x: -x[1])[:10]

        return {
            'mounted_spaces': mounted_count,
            'total_quantity': total_quantity,
            'distinct_codes': distinct_codes,
            'top_codes': top_codes,
            'per_code': code_counts,
        }
