from ...domain.mounted_product_list import MountedProductList
from ...domain.mounted_space_list import MountedSpaceList
from ...domain.base_rule import BaseRule
from ...domain.space import NotBulk, NotBlocked, NotChopp
from typing import Iterable
import math


class EmptySpaceRule(BaseRule):
    """Faithful port of the C# EmptySpaceRule.

    This implementation calls attributes and methods directly (no defensive checks),
    mirroring the C# control flow and helper usage.
    """

    def __init__(self, factor_converter= None):
        super().__init__()
        self._factor_converter = factor_converter

    def should_execute(self, context, item_predicate=None, mounted_space_predicate=None) -> bool:
        # If empty spaces are allowed, skip
        if context.get_setting('AllowEmptySpaces'):
            context.add_execution_log(f"Motivo - Configuração 'AllowEmptySpaces' está habilitada, regra não será executada")
            return False
        
        mounted_spaces = MountedSpaceList(context.mounted_spaces).NotBulk().NotBlocked().NotChopp()

        if context.Spaces and len(mounted_spaces) > 0:
            return True

        context.add_execution_log(f"Motivo - Não há baias vazias ou não há espaços montados elegíveis, regra não será executada")
        return False

    def execute(self, context):
        mounted_spaces = MountedSpaceList(context.mounted_spaces).NotBulk().NotBlocked().NotChopp()

        if context.get_setting('DistributeItemsOnEmptySpaces'):
            self._distribute_items_using_minimum_skus_quantity(context, mounted_spaces)
        else:
            self._distribute_items_by_packing_code(context, mounted_spaces)

    # --- Helpers ported from C# -------------------------------------------------
    def _distribute_items_using_minimum_skus_quantity(self, context, mounted_spaces: Iterable):
        min_skus = context.get_setting('MinimumQuantityOfSKUsToDistributeOnEmptySpaces')
        for space in list(context.Spaces):
            selected = self._get_selected_mounted_space(min_skus, mounted_spaces)
            if selected is None:
                break

            selected_mounted_product = self._get_selected_mounted_product(selected, context)
            self._move_partial_mounted_product(context, space, selected, selected_mounted_product)

    def _get_selected_mounted_space(self, minimum_quantity_of_skus, mounted_spaces: Iterable):
        # Apply filters like C#: WithMinimumQuantityOfItems, WithProducts, OrderByOccupationDesc
        filtered = (
            MountedSpaceList(mounted_spaces)
            .WithMinimumQuantityOfItems(minimum_quantity_of_skus)
            .WithProducts()
            .OrderByOccupationDesc()
        )
        
        if not filtered:
            return None
        
        # Group mounted spaces by distinct product count and choose best as C# logic
        grouped = {}
        for ms in filtered:
            prod_codes = [p.product.CodePromax for p in ms.get_first_pallet().get_products()]
            key = len(prod_codes)
            grouped.setdefault(key, []).append(ms)

        if not grouped:
            return None

        # C#: .Select(g => g.First()) then .OrderByDescending(ms => DifferentProductTypeQuantity)
        representatives = [group[0] for group in grouped.values()]
        ordered = sorted(representatives, key=lambda m: m.get_first_pallet().DifferentProductTypeQuantity, reverse=True)
        return ordered[0] if ordered else None

    def _get_selected_mounted_product(self, mounted_space, context):
        # group products by occupation then apply tie-breakers as C#
        products = mounted_space.get_first_pallet().get_products()
        groups = {}
        for p in products:
            occ = self._factor_converter.occupation(p, mounted_space.space.size, p.item, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))
            groups.setdefault(occ, []).append(p)

        occ_keys = sorted(groups.keys(), reverse=True)
        top_group = groups[occ_keys[0]] if occ_keys else []

        if len(top_group) > 1:
            # group by amount remaining
            amount_groups = {}
            for mp in top_group:
                amt = mp.order.items[0].amount_remaining
                amount_groups.setdefault(amt, []).append(mp)

            best_amt = max(amount_groups.keys())
            candidates = amount_groups[best_amt]

            # tiebreaker order: Chopp, Returnable, Disposable, IsotonicWater
            for t in (lambda x: x.product.is_chopp, lambda x: x.product.is_returnable, lambda x: x.product.is_disposable, lambda x: x.product.is_isotonic_water):
                for c in candidates:
                    if t(c):
                        return c

            return candidates[0]

        if top_group:
            return top_group[0]

        return None

    def _distribute_items_by_packing_code(self, context, mounted_spaces: Iterable):
        # for space in list(context.spaces):
        for space in list(context.Spaces):
            ordered = MountedSpaceList(mounted_spaces).OrderByDifferentPackingCodeQuantityDescAndProductQuantityDescAndOccupationDesc()
            # ordered = sorted(mounted_spaces, key=lambda m: ( -len(set([p.product.pack.packing_code for p in m.get_first_pallet().get_products()])), -sum([p.amount for p in m.get_first_pallet().get_products()]), -m.occupation ))
            for mounted in ordered:
                if self._try_move_mounted_product(context, space, mounted):
                    break

    def _try_move_mounted_product(self, context, space, mounted_space):
        grouped = {}
        for p in mounted_space.get_first_pallet().get_products():
            key = p.product.PackingGroup.PackingCode
            grouped.setdefault(key, []).append(p)

        groups = sorted(grouped.values(), key=lambda g: -sum([mp.amount for mp in g]))
        if len(groups) > 1:
            return self._try_move_mounted_product_when_various_packing_code(context, space, mounted_space, groups)
        else:
            return self._try_move_mounted_product_when_one_packing_code(context, space, mounted_space, groups[0] if groups else [])

    def _try_move_mounted_product_when_various_packing_code(self, context, space, mounted_space, mounted_products_group_by_packing_code):
        for mounted_products_same_packing_code in mounted_products_group_by_packing_code:
            if len(mounted_products_same_packing_code) > 1:
                dtos = self._get_mounted_product_with_occupation_dto(mounted_products_same_packing_code, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))
                if sum([d.OccupationBySpaceSize[space.size] for d in dtos]) <= space.size:
                    return context.domain_operations.move_mounted_products(context, space, mounted_space, [d.MountedProduct for d in dtos])
            else:
                mounted_product = next((x for x in mounted_products_same_packing_code if not x.product.is_layer), None)
                if mounted_product:
                    return self._move_partial_mounted_product(context, space, mounted_space, mounted_product)

        return False

    def _get_mounted_product_with_occupation_dto(self, mounted_products_same_packing_code, calculate_additional_occupation):
        class DTO:
            def __init__(self, mounted_product, occ_map):
                self.MountedProduct = mounted_product
                self.OccupationBySpaceSize = occ_map

        results = []
        sizes = [42, 35, 28, 21, 14]
        for x in sorted(mounted_products_same_packing_code, key=lambda k: -k.amount):
            occ_map = {}
            for s in sizes:
                occ_map[s] = self._factor_converter.occupation(x, s, x.item, calculate_additional_occupation)
            results.append(DTO(x, occ_map))
        return results

    def _try_move_mounted_product_when_one_packing_code(self, context, space, mounted_space, mounted_products_same_packing_code):
        # not_layer = [x for x in mounted_products_same_packing_code if not x.product.is_layer]
        not_layer = MountedProductList(mounted_products_same_packing_code).NotLayer().to_list()
        if len(not_layer) > 1:
            for item in MountedProductList(not_layer).order_by_amount_desc():
                # if self._move_partial_mounted_product(context, space, mounted_space, item):
                if context.domain_operations.move_mounted_product(context, space, mounted_space, item):
                    return True
            return False
        else:
            mounted_product = not_layer[0] if not_layer else None
            return self._move_partial_mounted_product(context, space, mounted_space, mounted_product)

    def _move_partial_mounted_product(self, context, space, mounted_space, mounted_product):
        if mounted_product is not None and (mounted_product.amount > mounted_product.product.PalletSetting.quantity_ballast or len(mounted_space.get_first_pallet().get_products()) > 1):
            quantity_to_move = self._get_quantity_to_move(mounted_product, mounted_space)
            return context.domain_operations.move_mounted_product(context, space, mounted_space, mounted_product, quantity_to_move)
        return False

    def _get_quantity_to_move(self, mounted_product, mounted_space):
        q = mounted_product.amount if mounted_product.amount <= mounted_product.product.PalletSetting.quantity_ballast else mounted_product.product.PalletSetting.quantity_ballast
        if mounted_product.amount > mounted_product.product.PalletSetting.quantity_ballast * 2:
            kept_ballast = math.floor(mounted_product.amount / 2 / mounted_product.product.PalletSetting.quantity_ballast)
            if kept_ballast == 0:
                kept_ballast = 1
            q = mounted_product.amount - kept_ballast * mounted_product.product.PalletSetting.quantity_ballast
        elif len(mounted_space.get_first_pallet().get_products()) == 1:
            q = math.ceil(q / 2)
        return int(q)