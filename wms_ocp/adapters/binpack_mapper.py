import math
from pathlib import Path
import pandas as pd 
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..domain.item import Item
from ..domain.context import Context
from ..domain.product import Package, BoxTemplate, Product
from ..domain.packing_group import PackingGroup
from ..domain.pallet_setting import PalletSetting   
from ..domain.item_marketplace import ItemMarketplace
from ..adapters.database  import extract_factors_from_row, extrair_codigo_tipo, apply_combined_groups_to_product

def _get_key(obj: Dict[str, Any], *names, default=None):
    if obj is None:
        return default
    for n in names:
        if n in obj:
            return obj[n]
        # case-insensitive
        for k in obj.keys():
            if k.lower() == n.lower():
                return obj[k]
    return default


class DeliveryOrderDetails:
    """Equivalente ao C# IDeliveryOrderDetails"""
    def __init__(self, DeliveryOrder: int, Customer: str, Amount: int, DetachedAmount: int):
        self.DeliveryOrder = DeliveryOrder
        self.Customer = Customer
        self.Amount = Amount
        self.DetachedAmount = DetachedAmount


class ItemInBox:
    """Equivalente ao C# IItemInBox"""
    def __init__(self, ItemCode: str, UnitAmountOfOne: int = 1, DeliveryOrders: Optional[List[DeliveryOrderDetails]] = None):
        self.ItemCode = ItemCode
        self.UnitAmountOfOne = UnitAmountOfOne
        self.DeliveryOrders = DeliveryOrders or []


class ItemDeliveryOrder:
    """Equivalente ao C# - agrupa items do XML por código"""
    def __init__(self):
        self.ItemCode: str = ""
        self.UnitAmountOfOne: int = 0
        self.DeliveryOrdersDetails: Dict[int, 'ItemDeliveryOrderDetails'] = {}


class ItemDeliveryOrderDetails:
    """Equivalente ao C# - detalhes de delivery order"""
    def __init__(self):
        self.Amount: int = 0
        self.DetachedAmount: int = 0
        self.Customer: str = ""


def GetGroupedItemsFromXml(grouped_orders) -> List[ItemDeliveryOrder]:
    """
    Equivalente ao C# GetGroupedItemsFromXml (linha 583)
    Agrupa items do context.Orders por código para distribuir nos packages/boxes
    """
    items_by_code = {}
    
    # Flatten all items from all orders
    for order in grouped_orders:
        if not hasattr(order, 'Items') or not order.Items:
            continue
            
        for item in order.Items:
            code = str(item.Code)
            
            if code not in items_by_code:
                items_by_code[code] = ItemDeliveryOrder()
                items_by_code[code].ItemCode = code
                items_by_code[code].UnitAmountOfOne = getattr(item, 'UnitAmount', 1)
                items_by_code[code].DeliveryOrdersDetails = {}
            
            # Get delivery order info
            delivery_order = getattr(order, 'DeliveryOrder', 0)
            customer = getattr(order, 'ClientCode', '')
            
            if delivery_order not in items_by_code[code].DeliveryOrdersDetails:
                items_by_code[code].DeliveryOrdersDetails[delivery_order] = ItemDeliveryOrderDetails()
                items_by_code[code].DeliveryOrdersDetails[delivery_order].Customer = customer
                items_by_code[code].DeliveryOrdersDetails[delivery_order].Amount = 0
                items_by_code[code].DeliveryOrdersDetails[delivery_order].DetachedAmount = 0
            
            items_by_code[code].DeliveryOrdersDetails[delivery_order].Amount += getattr(item, 'Amount', 0)
            items_by_code[code].DeliveryOrdersDetails[delivery_order].DetachedAmount += getattr(item, 'DetachedAmount', 0)
    
    return list(items_by_code.values())


def GetPackageDto(items_request: List[Any], package_code: int) -> Optional[Any]:
    """
    Equivalente ao C# GetPackageDto (linha 278)
    Busca metadados do item (ItemDto) para o package
    """
    if not items_request:
        return None
    
    for item_dto in items_request:
        if hasattr(item_dto, 'Code') and str(item_dto.Code) == str(package_code):
            return item_dto
    
    return None


def BuildPackageProduct(groups: List[Any], package_dto: Any, code: int, support_point: str = None) -> Package:
    """
    Equivalente ao C# BuildPackageProduct (linha 419)
    Cria produto Package com metadados (PackingGroup, Factors, PalletSetting)
    """
    package_product = Package()
    package_product.Code = code
    
    # Copia metadados do ItemDto
    if package_dto and hasattr(package_dto, 'Product'):
        original_product = package_dto.Product
        
        # PackingGroup
        if hasattr(original_product, 'PackingGroup'):
            package_product.PackingGroup = original_product.PackingGroup
        
        # Factors
        if hasattr(original_product, 'Factors'):
            package_product.Factors = original_product.Factors
        
        # PalletSetting
        if hasattr(original_product, 'PalletSetting'):
            package_product.PalletSetting = original_product.PalletSetting
        
        # GrossWeight
        if hasattr(original_product, 'GrossWeight'):
            package_product.GrossWeight = original_product.GrossWeight
        
        # Other properties
        if hasattr(original_product, 'Name'):
            package_product.Name = original_product.Name
        if hasattr(original_product, 'CodePromax'):
            package_product.CodePromax = original_product.CodePromax
    
    # SetGroupAssociations (C# linha 451)
    if groups and hasattr(package_product, 'PackingGroup') and package_product.PackingGroup:
        for group_combination in groups:
            if package_product.PackingGroup.GroupCode in group_combination:
                if hasattr(package_product, 'SetGroupAssociations'):
                    package_product.SetGroupAssociations(list(group_combination))
                break
    
    return package_product


def UpdatePackageWithDeliveryOrders(
    items_in_xml: List[ItemDeliveryOrder],
    package_code: int,
    package_quantity: int,
    detached_amount: int,
    package_product: Package,
    package_context_item: Item
):
    """
    Equivalente ao C# UpdatePackageWithDeliveryOrders (linha 250)
    Distribui packages entre delivery orders baseado em UnitsPerBox
    """
    remaining_quantity = package_quantity
    
    # Busca o item no XML pelo código
    xml_items = [x for x in items_in_xml if x.ItemCode == str(package_code)]
    
    for item_in_xml in xml_items:
        if remaining_quantity <= 0:
            break
        
        # Itera pelos delivery orders que têm quantidade suficiente para formar um package
        eligible_orders = [
            (delivery_order, details) 
            for delivery_order, details in item_in_xml.DeliveryOrdersDetails.items()
            if details.Amount >= package_product.UnitsPerBox
        ]
        
        for delivery_order, details in eligible_orders:
            if remaining_quantity <= 0:
                break
            
            customer = details.Customer if details.Customer else package_context_item.Customer
            value_order = details.Amount
            
            # Calcula quantos packages completos cabem
            multiplier = value_order // package_product.UnitsPerBox
            amount = multiplier * package_product.UnitsPerBox
            
            # Adiciona delivery order no package item
            if hasattr(package_context_item, 'AddDeliveryOrderClient'):
                package_context_item.AddDeliveryOrderClient(delivery_order, customer)
            
            if hasattr(package_context_item, 'AddClientQuantity'):
                package_context_item.AddClientQuantity(customer, amount)
            
            if hasattr(package_context_item, 'AddDeliveryOrder'):
                package_context_item.AddDeliveryOrder(delivery_order, amount, detached_amount)
            
            # Subtrai do XML
            item_in_xml.DeliveryOrdersDetails[delivery_order].Amount -= amount
            remaining_quantity -= amount


def GetPackages(
    grouped_orders,
    items_request: List[Any],
    groups: List[Any],
    boxed_map: Dict[str, Any],
    items_in_xml: List[ItemDeliveryOrder]
) -> List[Item]:
    """
    Equivalente ao C# GetPackages (linha 221)
    CRIA NOVOS Items tipo Package (não modifica existentes)
    """
    packages_result = _get_key(boxed_map, "result", "Result", default={}) or {}
    packages = _get_key(packages_result, "packages", "Packages", default=[]) or []
    
    created_packages = []
    
    for package in packages:
        code = _get_key(package, "code", "Code")
        quantity = _get_key(package, "quantity", "Quantity", default=0) or 0
        
        # Busca metadados do item (equivalente linha 233)
        package_dto = GetPackageDto(items_request, code)
        
        # Busca detached amount do XML (equivalente linha 235-236)
        detached_amount = 0
        unit_amount = quantity
        
        # CRIA NOVO produto Package (equivalente linha 238)
        package_product = BuildPackageProduct(groups, package_dto, code)
        if package_dto and hasattr(package_dto, 'ItemMarketplace') and getattr(package_dto.ItemMarketplace, 'UnitsPerBox', None) is not None:
            package_product.UnitsPerBox = int(package_dto.ItemMarketplace.UnitsPerBox or 0)
        else:
            package_product.UnitsPerBox = int(quantity or 0)
        
        # CRIA NOVO Item (equivalente linha 239)
        package_context_item = Item(
            Code=int(code) if str(code).isdigit() else code,
            Amount=int(quantity or 0),
            AmountRemaining=int(quantity or 0),
            Product=package_product,
            UnitAmount=unit_amount,
            Customer=package_dto.Customer 
        )
        
        # Atualiza delivery orders (equivalente linha 241)
        UpdatePackageWithDeliveryOrders(
            items_in_xml, 
            code, 
            quantity, 
            detached_amount, 
            package_product, 
            package_context_item
        )
        
        created_packages.append(package_context_item)
    
    return created_packages


def BuildBoxProduct(groups: List[Any], box_dto: Item, box_code: int, support_point: str = None) -> BoxTemplate:
    """
    Equivalente ao C# BuildBoxProduct (linha 426)
    Cria produto BoxTemplate com metadados
    """
    box_product = BoxTemplate()
    box_product.Code = box_code
    
    # Copia metadados do ItemDto
    if box_dto and box_dto.get('Product'):
        original_product = box_dto.get('Product')
        
        # PackingGroup
        if hasattr(original_product, 'PackingGroup'):
            box_product.PackingGroup = original_product.PackingGroup
        
        # Factors
        if hasattr(original_product, 'Factors'):
            box_product.Factors = original_product.Factors
        
        # PalletSetting
        if hasattr(original_product, 'PalletSetting'):
            box_product.PalletSetting = original_product.PalletSetting
        
        # GrossWeight
        if hasattr(original_product, 'GrossWeight'):
            box_product.GrossWeight = original_product.GrossWeight
        
        # Other properties
        if hasattr(original_product, 'Name'):
            box_product.Name = original_product.Name
    
    # SetGroupAssociations
    if groups and hasattr(box_product, 'PackingGroup') and box_product.PackingGroup:
        for group_combination in groups:
            if group_combination and hasattr(box_product.PackingGroup, 'GroupCode'):
                if box_product.PackingGroup.GroupCode in group_combination:
                    if hasattr(box_product, 'SetGroupAssociations'):
                        box_product.SetGroupAssociations(list(group_combination))
                    break
    
    box_product.LayerCode = 0
    return box_product


def AddItemsInBox(
    items_in_xml: List[ItemDeliveryOrder],
    box_sku_code: str,
    box_sku_quantity: int
) -> List[ItemInBox]:
    """
    Equivalente ao C# AddItemsInBox (linha 343)
    Cria ItemInBox com delivery orders para um SKU da box
    """
    items_in_box = []
    remaining_quantity = box_sku_quantity
    
    # Busca o item no XML
    xml_items = [x for x in items_in_xml if x.ItemCode == str(box_sku_code)]
    
    for item_in_xml in xml_items:
        if remaining_quantity <= 0:
            break
        
        delivery_order_details = []
        
        # Itera pelos delivery orders com quantidade disponível
        for delivery_order, details in item_in_xml.DeliveryOrdersDetails.items():
            if details.Amount <= 0:
                continue
            
            if remaining_quantity <= 0:
                break
            
            # Calcula amount (equivalente GetAmount linha 433)
            amount = min(remaining_quantity, details.Amount)
            customer = details.Customer
            detached_amount = details.DetachedAmount
            
            # Cria DeliveryOrderDetails
            item_box_delivery_order = DeliveryOrderDetails(
                DeliveryOrder=delivery_order,
                Customer=customer,
                Amount=amount,
                DetachedAmount=detached_amount
            )
            delivery_order_details.append(item_box_delivery_order)
            
            # Subtrai do XML
            item_in_xml.DeliveryOrdersDetails[delivery_order].Amount -= amount
            item_in_xml.DeliveryOrdersDetails[delivery_order].DetachedAmount = 0
            remaining_quantity -= amount
        
        # Cria ItemInBox
        if delivery_order_details:
            item_in_box_obj = ItemInBox(
                ItemCode=item_in_xml.ItemCode,
                UnitAmountOfOne=item_in_xml.UnitAmountOfOne,
                DeliveryOrders=delivery_order_details
            )
            items_in_box.append(item_in_box_obj)
    
    return items_in_box


def GetBoxes(
    items_request: List[Any],
    groups: List[Any],
    boxed_map: Dict[str, Any],
    items_in_xml: List[ItemDeliveryOrder],
    active_boxes: List[Any]
) -> List[Item]:
    """
    Equivalente ao C# GetBoxes (linha 299)
    CRIA NOVOS Items tipo BoxTemplate
    """
    boxes_result = _get_key(boxed_map, "result", "Result", default={}) or {}
    boxes = _get_key(boxes_result, "boxes", "Boxes", default=[]) or []
    
    created_boxes = []
    
    for box in boxes:
        box_code = _get_key(box, "code", "Code")
        skus = _get_key(box, "skus", "Skus", default=[]) or []
        
        # Primeiro: tentar recuperar metadados do item (ItemDto / BoxTemplate DTO) vindos de items_request
        box_dto = GetBoxDto(items_request, box_code) if items_request else None
        

        # Busca metadados da box (do ActiveBoxes - equivalente linha 305)
        box_dto = None
        if active_boxes:
            for active_box in active_boxes:
                if str(_get_key(active_box, "code", "Code")) == str(box_code):
                    box_dto = active_box#_get_key(active_box, "Product", "product")
                    break
        
        # CRIA NOVO produto BoxTemplate (equivalente linha 311)
        box_product = BuildBoxProduct(groups, box_dto, int(box_code) if str(box_code).isdigit() else box_code)
        
        # CRIA NOVO Item (equivalente linha 312)
        box_context_item = Item(
            Code=int(box_code) if str(box_code).isdigit() else box_code,
            Amount=1,
            AmountRemaining=1,
            Product=box_product,
            UnitAmount=1
        )
        
        # Processa SKUs e adiciona ItemsInBox (equivalente linha 313-315)
        all_items_in_box = []
        total_content_weight = 0.0
        for sku in skus:
            sku_code = _get_key(sku, "code", "Code")
            sku_qty = int(_get_key(sku, "quantity", "Quantity", default=0) or 0)

            # AddItemsInBox para cada SKU
            items_in_box = AddItemsInBox(items_in_xml, sku_code, sku_qty)
            all_items_in_box.extend(items_in_box)

            # Compute content weight from items_request (mirrors legado: weight = sum of contained items)
            for req_item in (items_request or []):
                if str(getattr(req_item, 'Code', '')) == str(sku_code):
                    prod = getattr(req_item, 'Product', None)
                    gw = getattr(prod, 'GrossWeight', None) if prod else None
                    if gw is not None:
                        try:
                            total_content_weight += float(gw) * sku_qty
                        except Exception:
                            pass
                    break

        # SetItemsInBox no produto (equivalente linha 315)
        if hasattr(box_product, 'SetItemsInBox'):
            box_product.SetItemsInBox(all_items_in_box)
        else:
            box_product.ItemsInBox = all_items_in_box

        # Override GrossWeight with content weight (sum of contained SKU weights).
        # Legado uses content weight for side balance (not the physical box container weight),
        # as evidenced by the report weight matching the sum of individual item weights.
        if total_content_weight > 0:
            box_product.GrossWeight = total_content_weight

        created_boxes.append(box_context_item)
    
    return created_boxes


def SetUnPalletizedItems(boxed_maps: List[Dict[str, Any]], all_items: List[Item]):
    """
    Equivalente ao C# SetUnPalletizedItems (linha 73)
    Marca items como UnPalletized baseado no resultado do binpack
    """
    if not boxed_maps:
        return
    
    unboxed_codes = set()
    
    for boxed_map in boxed_maps:
        result = _get_key(boxed_map, "result", "Result", default={}) or {}
        unboxed = _get_key(result, "unboxed_items", "UnboxedItems", default=[]) or []
        
        for un in unboxed:
            code = _get_key(un, "code", "Code", default=un) or un
            unboxed_codes.add(str(code))
    
    # Marca items como UnPalletized
    for item in all_items:
        if str(item.Code) in unboxed_codes:
            if hasattr(item, 'Product') and hasattr(item.Product, 'SetUnPalletized'):
                try:
                    item.Product.SetUnPalletized()
                except Exception:
                    pass

def GetBoxDto(items_request: List[Any], box_code: int) -> Optional[Any]:
    """
    Busca metadados (ItemDto / BoxTemplate DTO) para a box, equivalente ao C# GetBoxTemplateDto/GetPackageDto.
    """
    if not items_request:
        return None
    for item_dto in items_request:
        if hasattr(item_dto, 'Code') and str(item_dto.Code) == str(box_code):
            return item_dto

    return None

def BuildMarketplaces(
    binpack_json: Iterable[Dict[str, Any]],
    grouped_orders,
    items_request: List[Any],
    groups: List[Any],
    active_boxes: List[Any],
    context: Optional[Context] = None
) -> Tuple[List[Item], List[str]]:
    """
    Equivalente ao C# BuildMarketplaces (linha 598)
    CRIA NOVOS Items tipo Package/BoxTemplate e adiciona no context
    Retorna (created_items, marketplace_item_codes)
    """
    created_items: List[Item] = []
    marketplace_item_codes: List[str] = []
    
    # GetGroupedItemsFromXml (equivalente linha 612)
    items_in_xml = GetGroupedItemsFromXml(grouped_orders)
    
    for boxed_map in binpack_json or []:
        # HasPackages (equivalente linha 614)
        result = _get_key(boxed_map, "result", "Result", default={}) or {}
        has_packages = bool(_get_key(result, "packages", "Packages", default=[]))
        
        if has_packages:
            # GetPackages (equivalente linha 616)
            packages = GetPackages(grouped_orders, items_request, groups, boxed_map, items_in_xml)
            
            # allItems.AddRange (equivalente linha 617)
            created_items.extend(packages)
            
            # NÃO adiciona no context aqui - será adicionado em BuildItems
            # No C# adiciona em allItems (lista temporária) e depois cria a order
            
            # marketplaceItems.AddRange (equivalente linha 618)
            marketplace_item_codes.extend([str(p.Code) for p in packages])
        
        # HasBoxes (equivalente linha 621)
        has_boxes = bool(_get_key(result, "boxes", "Boxes", default=[]))
        
        if has_boxes:
            # GetBoxes (equivalente linha 623)
            boxes = GetBoxes(items_request, groups, boxed_map, items_in_xml, active_boxes)
            
            # allItems.AddRange (equivalente linha 624)
            created_items.extend(boxes)
            
            # NÃO adiciona no context aqui - será adicionado em BuildItems
            # No C# adiciona em allItems (lista temporária) e depois cria a order
            
            # marketplaceItems.AddRange - códigos da box e dos SKUs dentro (equivalente linha 625)
            for box in boxes:
                marketplace_item_codes.append(str(box.Code))
                if hasattr(box.Product, 'ItemsInBox'):
                    for item_in_box in box.Product.ItemsInBox:
                        marketplace_item_codes.append(item_in_box.ItemCode)
    
    return (created_items, list(set(marketplace_item_codes)))


def ExceptMarketplaces(item_code: str, marketplace_item_codes: List[str]) -> bool:
    """
    Equivalente ao C# ExceptMarketplaces (linha 640)
    Retorna True se o item NÃO é marketplace (deve ser processado)
    Retorna False se o item É marketplace (deve ser ignorado)
    """
    return str(item_code) not in marketplace_item_codes


def BuildItems(
    context: Context,
    marketplace_item_codes: List[str],
    created_items: List[Item]
) -> None:
    """
    Equivalente ao C# BuildItems (linha 81)
    FILTRA items originais removendo os marketplace
    DISTRIBUI created_items (Package/BoxTemplate) nas orders corretas baseado em DeliveryOrders
    """
    if not context or not hasattr(context, 'Orders'):
        return
    
    # 1. FILTRA items originais de cada order - remove marketplace
    for order in context.Orders:
        if not hasattr(order, 'Items') or not order.Items:
            continue
        
        filtered_items = []
        
        for item in order.Items:
            item_code = str(item.Code)
            
            # Se NÃO é marketplace, mantém (item normal)
            if ExceptMarketplaces(item_code, marketplace_item_codes):
                filtered_items.append(item)
            # Se É marketplace, remove (será substituído por Package/BoxTemplate)
        
        # Atualiza lista com items filtrados
        order.Items = filtered_items
    
    # 2. DISTRIBUI created_items nas orders corretas baseado em DeliveryOrders
    # C#: cada Item tem DeliveryOrders dict que indica quais orders ele pertence
    # Distribui cada created_item para a(s) order(s) apropriada(s)
    
    for idx, ci in enumerate(created_items):
        # Garantir que temos um Item; se for um Product (ou outro), enclose em Item
        created_item = ci
        if not isinstance(created_item, Item):
            try:
                prod = created_item
                created_item = Item(
                    Code=int(getattr(prod, 'Code', 0)) if str(getattr(prod, 'Code', 0)).isdigit() else getattr(prod, 'Code', 0),
                    Amount=1,
                    AmountRemaining=1,
                    Product=prod,
                    UnitAmount=getattr(prod, 'UnitsPerBox', 1) or 1
                )
                # replace in list so clones reference an Item
                created_items[idx] = created_item
            except Exception:
                # se não for possível encapsular, pula
                continue

        # Obtém delivery orders do item
        delivery_orders = []

        # Tenta pegar DeliveryOrdersWithAmount (retorna lista de delivery orders com quantidade)
        if hasattr(created_item, 'DeliveryOrdersWithAmount'):
            try:
                delivery_orders = list(created_item.DeliveryOrdersWithAmount())
            except Exception:
                delivery_orders = []

        # Fallback: acessa dicionário _delivery_orders diretamente
        if not delivery_orders:
            try:
                delivery_dict = getattr(created_item, '_delivery_orders', {})
                delivery_orders = [k for k, v in delivery_dict.items() if v > 0]
            except Exception:
                delivery_orders = []

        # BoxTemplate: assign to the correct orders based on ItemsInBox.DeliveryOrders
        if getattr(created_item, 'Product', None) and getattr(created_item.Product, 'ItemsInBox', None):
            # Collect all delivery order numbers from the items inside the box
            box_delivery_orders = set()
            for item_in_box in created_item.Product.ItemsInBox:
                for do in (getattr(item_in_box, 'DeliveryOrders', None) or []):
                    dov = getattr(do, 'DeliveryOrder', None)
                    if dov is not None:
                        box_delivery_orders.add(dov)

            if box_delivery_orders:
                added = False
                for order in context.Orders:
                    order_delivery = getattr(order, 'DeliveryOrder', getattr(order, 'delivery_order', None))
                    if order_delivery in box_delivery_orders:
                        if not any(created_item is ei for ei in order.Items):
                            if added:
                                from copy import deepcopy
                                order.Items.append(deepcopy(created_item))
                            else:
                                order.Items.append(created_item)
                                added = True
                if not added:
                    # fallback: first order
                    if context.Orders:
                        context.Orders[0].Items.append(created_item)
            else:
                # no delivery info: fallback to first order
                if context.Orders:
                    context.Orders[0].Items.append(created_item)
            continue

        # Adiciona o item em TODAS as orders que correspondem aos delivery_orders
        for order in context.Orders:
            order_delivery = getattr(order, 'DeliveryOrder', getattr(order, 'delivery_order', None))

            if order_delivery in delivery_orders:
                # Verifica se já foi adicionado nesta order
                if any(created_item is existing_item for existing_item in order.Items):
                    continue

                # Verifica se já adicionamos este item em outra order (para decidir clonar)
                already_added_elsewhere = any(
                    any(created_item is ei for ei in o.Items)
                    for o in context.Orders if o is not order
                )

                if already_added_elsewhere:
                    # Clona o item para esta order
                    if hasattr(created_item, 'Clone'):
                        cloned_item = created_item.Clone()
                    else:
                        from copy import deepcopy
                        cloned_item = deepcopy(created_item)
                    order.Items.append(cloned_item)
                else:
                    order.Items.append(created_item)


# ============== FUNÇÃO PRINCIPAL ==============

def apply_binpack_json(
    binpack_json: Iterable[Dict[str, Any]],
    context: Optional[Context] = None,
    items_request: Optional[List[Any]] = None,
    groups: Optional[List[Any]] = None,
    active_boxes: Optional[List[Any]] = None
) -> Tuple[List[Item], List[str]]:
    """
    Função principal - wrapper para BuildMarketplaces + BuildItems
    100% fiel ao C# ToEnumerableOfIOrder
    
    Args:
        binpack_json: Resultado da API de binpack (BoxedMapDto[])
        context: Context com orders carregadas
        items_request: Lista de ItemDto (metadados do BD)
        groups: Lista de GroupCombinationDto
        active_boxes: Lista de boxes ativas
    
    Returns:
        Tuple (created_items, marketplace_item_codes)
    """
    # Simula grouped_orders do context (no C# vem do GetGroupedXmlOrders)
    grouped_orders = []
    if context and hasattr(context, 'Orders'):
        grouped_orders = context.Orders
    
    # 1. BuildMarketplaces - CRIA novos Package/BoxTemplate (C# linha 63)
    created_items, marketplace_item_codes = BuildMarketplaces(
        binpack_json,
        grouped_orders,
        items_request or [],
        groups or [],
        active_boxes or [],
        context
    )
    
    # 2. BuildItems - FILTRA items originais E ADICIONA created_items (C# linha 65)
    BuildItems(context, marketplace_item_codes, created_items)
    
    # 3. SetUnPalletizedItems (C# linha 67)
    if context and hasattr(context, 'Orders'):
        all_items = []
        for order in context.Orders:
            if hasattr(order, 'Items'):
                all_items.extend(order.Items)
        
        SetUnPalletizedItems(binpack_json, all_items)
    
    return (created_items, marketplace_item_codes)


def BuildActiveBoxesFromBinpack(binpack_json, combined_groups):
    """
    Constrói e retorna `active_boxes` a partir do resultado do binpack e do DataFrame do catálogo.

    Args:
    - binpack_json: lista/iterável com os boxed_map retornados pelo binpack.

    Returns:
    - lista de dict-like com chaves ('code','length','width','height','box_slots','box_slot_diameter','Product')
        onde `Product` é um `BoxTemplate` enriquecido com PackingGroup/PalletSetting/ItemMarketplace quando disponível.
    """
    from ..domain.product import BoxTemplate

    base_dir = Path(__file__).parent.parent / 'database'
    
    df = pd.read_csv(base_dir / "boxes_completo_merge.csv")
    df = df.where(pd.notnull(df), None).astype(object)
    df  = df.set_index("Código")
    df_boxs = df[(df.WarehouseId=='401') | (df.WarehouseId==401)]

        
    active_boxes = []
    seen = set()

    for boxed_map in binpack_json or []:
        result = (boxed_map or {}).get('result') or {}
        boxes = result.get('boxes') or []
        for b in boxes:
            box_code = b.get('code')
            if box_code is None:
                continue
            key = str(box_code)
            if key in seen:
                continue
            seen.add(key)

            # tenta buscar metadados no catálogo
            try:
                row = df_boxs[(df_boxs['ItemCode'] == int(key) ) | (df_boxs['ItemCode'] == str(key) )].iloc[0]#.to_dict()
            except Exception:
                row = None

            # monta produto BoxTemplate mínimo
            box_prod = BoxTemplate()
            try:
                box_prod.Code = int(key)
            except Exception:
                box_prod.Code = key

            if row is not None:
                # preenchimentos seguros (colunas possíveis)
                box_prod.Name = row.get('Descrição') or row.get('Nome Catálogo') or row.get('Descrição do item') or getattr(box_prod, 'Name', None)
                box_prod.CodePromax = row.get('Código Unb') or getattr(box_prod, 'CodePromax', None)
                try:
                    gw = row.get('Peso bruto do item') or row.get('Peso bruto')
                    if gw is not None:
                        box_prod.GrossWeight = float(gw)
                except Exception:
                    pass 

                box_prod.PackingGroup = PackingGroup(
                    Code=row.get('Código embalagem', None),
                    PackingCode=row.get('Código tipo embalagem', None),
                    PackingName=row.get('Embalagem', None),
                    GroupCode=row.get('Grupo', None),
                    SubGroupCode=row.get('Subgrupo', None),
                    ProductTypeCode=extrair_codigo_tipo(row.get('Embalagem/Tipo produto', "")),
                    ProductTypeName=row.get('Nome Catálogo', None),
                    IsGlobal=row.get('Ativo', None),
                    IsRegional=None,
                    WarehouseUnbCode=row.get('Armazém', None),
                    WmsId=None,
                    CatalogId=row.get('Id Catálogo', None)
                )

                box_prod.PalletSetting = PalletSetting(
                    Quantity=row.get('Quantidade Palete', None),
                    BulkPriority=row.get('Prioridade Palete', None) if "Prioridade Palete" in row else None,
                    QuantityDozen=row.get('Quantidade Palete Dúzia', None),
                    QuantityBallast=row.get('Quantidade de Lastros/Camadas', None),
                    QuantityBallastMin=row.get('Quantidade Mínima Lastros/Camadas', 0),
                    Layers= row.get('Camadas', None),
                    IncludeTopOfPallet=row.get('Topo Palete', None),
                    BasePallet=row.get('Base palete', None)
                )

                
    
                box_prod.LayerCode = 0#row.get('Camadas', None)
                box_prod.Factors = extract_factors_from_row(row) 
                # Additional occupation settings (Product properties, not Item)
                box_prod.CalculateAdditionalOccupation = bool(row.get("Ocupação extra", False))
                box_prod.BallastQuantity = int(row.get("Quantidade de Lastros/Camadas", 0) or 0)
                
                box_prod.factor = row.get("Fator", None)

                apply_combined_groups_to_product(box_prod, combined_groups)

                raw_box_type = row.get("Tipo Caixa", None)
                raw_units_per_box = row.get("Quantidade de unidades por caixa", None)

                # cria o ItemMarketplace a partir dos valores crus
                if raw_box_type is not None:
                    print(f"[INFO] Valor bruto de Tipo Caixa: {raw_box_type}, Code: {box_code}")
                    if raw_units_per_box is None or (math.isnan(raw_units_per_box)):
                        raw_units_per_box=0
                    item_marketplace = ItemMarketplace.from_row_values(raw_box_type, raw_units_per_box)
                    item_marketplace.item = box_code
                    box_prod.ItemMarketplace = item_marketplace

            # dict compatível com _get_key e com BuildBoxProduct (tem 'Product')
            wrapped = {
                "code": box_prod.Code,
                "length": b.get('length', 0),
                "width": b.get('width', 0),
                "height": b.get('height', 0),
                "box_slots": b.get('box_slots', 0),
                "box_slot_diameter": b.get('box_slot_diameter', 0),
                "Product": box_prod
            }
            active_boxes.append(wrapped)

    return active_boxes
