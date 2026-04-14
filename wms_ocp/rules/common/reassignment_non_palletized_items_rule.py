from decimal import Decimal
from typing import Iterable, List

from ...domain.mounted_space_list import MountedSpaceList
from ...domain.space_size import SpaceSize

from ...domain.itemList import ItemList
from ...domain.base_rule import BaseRule
from ...domain.context import Context


class ReassignmentNonPalletizedItemsRule(BaseRule):
    """Faithful port of C# ReassignmentNonPalletizeditemsRule.

    This implementation calls domain methods directly (no attribute existence checks)
    to keep control flow identical to the original C# rule. It favors readability
    and keeps small helper methods extracted from the original class.
    """

    def __init__(self, factor_converter=None):
        super().__init__(name='ReassignmentNonPalletizeditemsRule')
        self._can_split_item = False
        self._factor_converter = factor_converter

    def debug(self, message: str, context: Context = None):
        # preserve a light-weight debug hook similar to WriteLogDebug
        # call logger.debug directly (faithful to C# behavior)
        try:
            context.add_execution_log(message)
            return
        except Exception:
            # fallback to stdout if logger not available
            print(f"[{self.name}] {message}")

    def enable_split_item(self):
        self._can_split_item = True
        return self

    def should_execute(self, context: Context, item_predicate=None, mounted_space_predicate=None) -> bool:
        if not context.get_setting('ReassignmentOfNonPalletizedItems'):
            context.add_execution_log("Regra de reatribuição de itens não paletizados desativada, não será executada")
            return False

        if not ItemList(context.get_items()).with_amount_remaining().any():
            context.add_execution_log("Não foram encontrados itens não paletizados, a regra não será executada")
            return False

        return True

    def execute(self, context: Context) -> Context:
        # Mirrors C#: detect AS vs Route orders by examining Customer field
        as_orders = [
            o for o in context.orders
            if any(y.customer is not None and y.customer.strip() != "" for y in o.items)
        ]
        if as_orders:
            self.debug("Itens não paletizados AS")
            self._reassignment_non_palletized_items(context, as_orders)

        route_orders = [
            o for o in context.orders
            if any(y.customer is None or y.customer.strip() == "" for y in o.items)
        ]
        if route_orders:
            self.debug("Itens não paletizados Rota")
            self._reassignment_non_palletized_items(context, route_orders)

        return context

    def GetNonPalletizedItems(self, context: Context, order):
        if self._can_split_item:
            return ItemList(context.get_items_palletizable_by_order(order)).not_marketplace().with_amount_remaining()

        return ItemList(context.get_items_palletizable_by_order(order)).with_amount_remaining()
        
    def _reassignment_non_palletized_items(self, context: Context, orders: List):
        for order in orders:
            # non_palletized_items = ItemList(context.get_items_palletizable_by_order(order)).with_amount_remaining()
            non_palletized_items = self.GetNonPalletizedItems(context, order)
            
            if not non_palletized_items.any():
                continue
            
            # calculate and set default occupation per item (mirror C# behavior)
            self._calculate_and_set_occupation_default(context, non_palletized_items, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))

            # if context.kind == 'AS':
            mounted_spaces = MountedSpaceList(context.mounted_spaces).matching(lambda x: x.Order == order).NotBulk().OrderByOccupation()
            # elif context.kind == 'Route':
            #     mounted_spaces = MountedSpaceList(context.mounted_spaces).NotBulk().OrderByOccupation()

            customer = ItemList(order.items).First().Customer if ItemList(order.items).Any() else None
            self.debug(f"Procurando espaços para adicionar os itens não paletizados - {('Cliente: ' + customer) if customer else 'Rota'}", context)

            # sort by ocp default per uni 42 desc (C# uses OrderByDescending)
            for item in non_palletized_items.OrderByDescending(lambda x: x.OcpDefaultPerUni42):
                self._add_item_in_mounted_space(context, mounted_spaces, item)

    def _add_item_in_mounted_space(self, context: Context, mounted_spaces: Iterable, item):
        if self._can_split_item:
            self._add_splitted_item_in_mounted_space(context, mounted_spaces, item)
        else:
            self._add_item_amount_remaining_in_mounted_space(context, mounted_spaces, item)

    def _add_splitted_item_in_mounted_space(self, context: Context, mounted_spaces: Iterable, item):

        for mounted_space in mounted_spaces.OrderByDescending(lambda s: s.occupation_remaining):
            quantity = int(self._factor_converter.quantity_to_remaining_space(context, mounted_space, item, item.amount_remaining))

            if quantity > 0 and context.domain_operations.can_add(context, mounted_space, item, quantity, True):
                self._add_item_quantity_in_mounted_space(context, item, quantity, mounted_space)

    def _add_item_amount_remaining_in_mounted_space(self, context: Context, mounted_spaces: Iterable, item):

        available = MountedSpaceList(mounted_spaces).matching(lambda space: space.OccupationRemaining > 0 \
                                        and context.domain_operations.can_add(context, space, item, item.amount_remaining, True))\
                                        .ordered_by_descending(lambda s: s.OccupationRemaining).first_or_default()

        if available is not None:
            self._add_item_quantity_in_mounted_space(context, item, item.amount_remaining, available)

    def _add_item_quantity_in_mounted_space(self, context: Context, item, item_quantity: int, mounted_space):
        
        first_layer = mounted_space.get_next_layer()
        quantity_of_layer = item.product.get_quantity_of_layer_to_space(mounted_space.space.size, item_quantity)
        occupation = self._factor_converter.occupation(item_quantity, mounted_space.space.size, item, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))

        self.debug(f"Adicionando item {item.product.code}-{item.product.name}, ocupacao {occupation} no pallet {mounted_space.space.number}/{mounted_space.space.sideDesc}", context)
        context.AddProduct(mounted_space.space, item, item_quantity, first_layer, quantity_of_layer, occupation)

    def _calculate_and_set_occupation_default(self, context: Context, items, calculate_additional_occupation: bool):
        
        self.debug("Calculando ocupação dos itens não paletizados")
        for item in items:
            ocp_default = self._factor_converter.occupation(item.amount_remaining, Decimal(42), item, calculate_additional_occupation)
            item.SetOcpDefaultPerUni42(ocp_default)

