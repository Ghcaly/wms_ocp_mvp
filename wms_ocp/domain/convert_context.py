from __future__ import annotations
from typing import Any, Dict, List, Optional
from copy import deepcopy
import logging
from .pallet import Pallet, ItemPallet

logger = logging.getLogger(__name__)


def _safe_get(obj: Any, *names, default=None):
    """Return the first attribute or key present in obj for any name in names.

    Works for attributes and dict keys. If name is callable on obj it will be
    called (useful for Context.get_all_items style methods).
    """
    if obj is None:
        return default

    for name in names:
        # attribute
        try:
            if hasattr(obj, name):
                val = getattr(obj, name)
                if callable(val):
                    try:
                        return val()
                    except TypeError:
                        # method requires params - skip
                        return val
                return val
        except Exception:
            pass

        # dict style
        try:
            if isinstance(obj, dict) and name in obj:
                return obj[name]
        except Exception:
            pass

    return default


def convert_context(context: Any, request: Any = None) -> Dict[str, Any]:
    """Main entry point mirroring C# ConvertContext.

    Returns a dict with keys:
      - pallets: list of Pallet objects (or their to_dict() if consumer prefers)
      - not_palletized_products: list of dicts for non-palletized products
      - products: a shallow copy of context.products if present (template products)
      - message: optional diagnostic message
    """
    # Prepare base map
    products = _safe_get(context, 'products', 'Produtos', default=[])
    map_out: Dict[str, Any] = {
        'pallets': [],
        'not_palletized_products': [],
        'products': deepcopy(products) if products else [],
        'message': None,
    }

    # Convert mounted spaces (create pallets and add products)
    try:
        convert_mounted_spaces(context, map_out)
    except Exception as e:  # defensive: don't crash the pipeline
        logger.exception("convert_mounted_spaces failed: %s", str(e))
        map_out['message'] = (map_out.get('message') or '') + f" convert_mounted_spaces error: {e}"

    # Convert non-mounted products (not paletized)
    try:
        convert_not_mounted_products(context, map_out)
    except Exception as e:
        logger.exception("convert_not_mounted_products failed: %s", str(e))
        map_out['message'] = (map_out.get('message') or '') + f" convert_not_mounted_products error: {e}"

    return map_out


def convert_mounted_spaces(context: Any, map_out: Dict[str, Any]) -> None:
    """Iterate mounted spaces and create pallets accordingly.

    The C# code orders mounted spaces placing complex-load ones first; we do
    a defensive ordering by checking mounted_space.product flags when present.
    """
    mounted_spaces = _safe_get(context, 'mounted_spaces', 'MountedSpaces', default=[])

    # If there's a helper method GetComplexLoadCustomer in context use it
    complex_load_customer = _safe_get(context, 'get_complex_load_customer', 'GetComplexLoadCustomer')
    complex_delivery_order = _safe_get(context, 'get_complex_delivery_order', 'GetComplexDeliveryOrder')

    # Sort mounted spaces: those with any product flagged 'complex_load' first
    def _is_complex(ms):
        prods = _safe_get(ms, 'get_products', 'GetProducts', 'products', default=[])
        try:
            return any(getattr(p, 'complex_load', False) or getattr(p, 'ComplexLoad', False) for p in prods)
        except Exception:
            return False

    try:
        mounted_spaces_sorted = sorted(mounted_spaces, key=lambda x: not _is_complex(x))
    except Exception:
        mounted_spaces_sorted = mounted_spaces

    for mounted_space in mounted_spaces_sorted:
        pallet = add_pallet(map_out, mounted_space)
        add_product(context, map_out, mounted_space, pallet, complex_load_customer, complex_delivery_order)


def _find_or_create_pallet(map_out: Dict[str, Any], number: Optional[int], side: Optional[str]) -> Pallet:
    # Find by nrBaiaGaveta and cdLado
    for p in map_out['pallets']:
        try:
            if getattr(p, 'nrBaiaGaveta', None) == number and getattr(p, 'cdLado', None) == side:
                return p
        except Exception:
            # p may be a dict
            if (isinstance(p, dict) and p.get('nrBaiaGaveta') == number and p.get('cdLado') == side):
                return p

    # Not found: create
    new_pallet = Pallet(cdLado=side, nrBaiaGaveta=number)
    # allow dynamic extra attributes similar to C# Pallet (Cheio, Ocupacao, Lastro...)
    map_out['pallets'].append(new_pallet)
    return new_pallet


def add_pallet(map_out: Dict[str, Any], mounted_space: Any) -> Pallet:
    """Mirror AddPallet: locate or create a Pallet object and fill bay-level metadata.

    This function is defensive: it will try multiple attribute names and will
    attach extra metadata fields dynamically to the Pallet instance.
    """
    space = _safe_get(mounted_space, 'space', 'Space', default=None)
    number = _safe_get(space, 'number', 'Number', default=_safe_get(mounted_space, 'space_number', 'SpaceNumber'))
    side = _safe_get(space, 'side', 'Side', default=_safe_get(mounted_space, 'side', 'CdLado'))

    pallet = _find_or_create_pallet(map_out, number, side)

    # Set bay metadata similar to C#: Cheio, Ocupacao, Lastro
    try:
        ocupado = _safe_get(mounted_space, 'occupation', 'Occupation', 'Ocupacao')
        setattr(pallet, 'Ocupacao', ocupado)
    except Exception:
        pass

    try:
        full = _safe_get(mounted_space, 'full', 'Full', 'Cheio') or _safe_get(mounted_space, 'blocked', 'Blocked')
        setattr(pallet, 'Cheio', bool(full))
    except Exception:
        pass

    # Lastro: sum of QuantityOfLayers across containers/products if present
    try:
        products = _safe_get(mounted_space, 'get_products', 'GetProducts', 'products', default=[])
        lastro = 0
        for c in products:
            lastro += int(_safe_get(c, 'quantity_of_layers', 'QuantityOfLayers', default=0) or 0)
        setattr(pallet, 'Lastro', lastro)
    except Exception:
        pass

    # DocumentNumbersCrossDock and LicensePlateCrossDock (distinct values)
    try:
        prods_with_amount = [p for p in products if (getattr(p, 'amount', None) or getattr(p, 'Amount', None) or getattr(p, 'Quantity', None))]
        docs = set()
        plates = set()
        for p in prods_with_amount:
            order = _safe_get(p, 'order', 'Order', default=None)
            if order:
                docs.update(set([_safe_get(order, 'map_number', 'MapNumber', default=None)]))
                plates.update(set([_safe_get(order, 'license_plate', 'LicensePlate', default=None)]))

        setattr(pallet, 'DocumentNumbersCrossDock', [d for d in docs if d is not None])
        setattr(pallet, 'LicensePlateCrossDock', [lp for lp in plates if lp is not None])
    except Exception:
        pass

    # Container base type / group info (best-effort)
    try:
        containers = _safe_get(mounted_space, 'containers', 'Containers', default=[])
        for container in containers:
            product_base = _safe_get(container, 'product_base', 'ProductBase', default=None)
            if product_base:
                group = _safe_get(product_base, 'packing_group', 'PackingGroup', default=None)
                if group:
                    setattr(pallet, 'CodigoGrupoBase', _safe_get(group, 'group_code', 'GroupCode'))
                    setattr(pallet, 'CodigoSubGrupoBase', _safe_get(group, 'sub_group_code', 'SubGroupCode'))
                cont_type = _safe_get(product_base, 'container_type', 'ContainerType')
                if cont_type is not None:
                    setattr(pallet, 'TipoBase', cont_type)
            # If container looks like a pallet and has Bulk flag
            if _safe_get(container, 'bulk', 'Bulk', default=False):
                setattr(pallet, 'Fechado', True)
    except Exception:
        pass

    return pallet


def add_product(context: Any, map_out: Dict[str, Any], mounted_space: Any, pallet: Pallet, complex_load_customer: Any, complex_delivery_order: Any) -> None:
    """Mirror AddProduct: iterate mounted products and add them to the pallet.

    We implement a simplified but behaviorally similar approach:
      - If an item is a box template containing ItemsInBox, expand them
      - Otherwise, add a single entry per mounted product with computed quantities
    """
    mounted_products = _safe_get(mounted_space, 'get_products', 'GetProducts', 'products', default=[])

    # Try to obtain ordering flag
    mounted_products_iter = mounted_products
    box_number = 1

    for mp in mounted_products_iter:
        item = _safe_get(mp, 'item', 'Item', default=mp)

        # Detect box template by presence of items_in_box / ItemsInBox
        items_in_box = _safe_get(mp, 'items_in_box', 'ItemsInBox', default=None)
        if items_in_box:
            for child in items_in_box:
                try:
                    ip = ItemPallet()
                    ip.sqEntrega = _safe_get(child, 'delivery_order', 'DeliveryOrder')
                    ip.cdItem = int(_safe_get(child, 'item_code', 'ItemCode', default=_safe_get(child, 'code')) or 0)
                    ip.qtUnVenda = int(_safe_get(child, 'amount', 'Amount', default=0) or 0)
                    ip.sqMontagem = _safe_get(mp, 'assembly_sequence', 'AssemblySequence')
                    pallet.add_item(ip)
                except Exception:
                    logger.exception("failed to add boxed item for pallet %s", getattr(pallet, 'nrBaiaGaveta', None))
            box_number += 1
            continue

        # Default non-boxed flow
        try:
            ip = ItemPallet()
            # Prefer delivery order sequence if present
            ip.sqEntrega = _safe_get(mp, 'delivery_order', 'DeliveryOrder') or _safe_get(item, 'delivery_order', 'DeliveryOrder')
            # Product code
            code = (_safe_get(mp, 'product', 'Product', default=None) and _safe_get(_safe_get(mp, 'product', 'Product'), 'code', 'Code'))
            if code is None:
                code = _safe_get(item, 'product', 'Product', default=None) and _safe_get(_safe_get(item, 'product', 'Product'), 'code', 'Code')
            ip.cdItem = int(code) if code is not None else None
            # Quantities
            amount = _safe_get(mp, 'amount', 'Amount') or _safe_get(item, 'amount_remaining', 'AmountRemaining', default=None) or _safe_get(item, 'amount', 'Amount', default=0)
            try:
                ip.qtUnVenda = int(amount)
            except Exception:
                ip.qtUnVenda = amount
            ip.sqMontagem = _safe_get(mp, 'assembly_sequence', 'AssemblySequence') or _safe_get(item, 'assembly_sequence', 'AssemblySequence')

            pallet.add_item(ip)
        except Exception:
            logger.exception("add_product: failed to create ItemPallet for pallet %s", getattr(pallet, 'nrBaiaGaveta', None))


def convert_not_mounted_products(context: Any, map_out: Dict[str, Any]) -> None:
    """Mirror ConvertNotMountedProducts: produce not_palletized_products list.

    This function iterates over context.get_all_items (or 'items' / 'GetAllItems') and
    adds non-palletized product dicts including computed quantities.
    """
    get_all_items = _safe_get(context, 'get_all_items', 'GetAllItems', default=None)
    if callable(get_all_items):
        items = get_all_items()
    else:
        items = _safe_get(context, 'items', 'Items', default=_safe_get(context, 'orders', 'Orders', default=[]))

    # Flatten orders -> items if necessary
    if items and isinstance(items, list) and items and _safe_get(items[0], 'product', 'Product', default=None) is None and _safe_get(items[0], 'items', default=None):
        # items is probably a list of orders
        try:
            flattened = []
            for o in items:
                flattened.extend(_safe_get(o, 'items', 'Items', default=[]))
            items = flattened
        except Exception:
            pass

    for item in items or []:
        try:
            amt = _safe_get(item, 'amount_remaining', 'AmountRemaining', 'amount', 'Amount', default=0) or 0
            detached = _safe_get(item, 'detached_amount', 'DetachedAmount', default=0) or 0

            if (amt == 0 and detached == 0):
                continue

            product_code = _safe_get(item, 'product', 'Product', default=None)
            if product_code:
                product_code = _safe_get(product_code, 'code', 'Code', default=product_code)

            nonp = {
                'cdItem': int(product_code) if product_code is not None and str(product_code).isdigit() else product_code,
                'qtUnVenda': int(amt) if isinstance(amt, (int, float, str)) and str(amt).isdigit() else amt,
                'qtUnVendaAvulsa': int(detached) if isinstance(detached, (int, float, str)) and str(detached).isdigit() else detached,
                'segregated': bool(_safe_get(item, 'realocated', 'Realocated', default=False)),
            }
            map_out['not_palletized_products'].append(nonp)
        except Exception:
            logger.exception("convert_not_mounted_products: failed for item %s", item)
