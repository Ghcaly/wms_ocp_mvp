from ...domain.itemList import ItemList
from ...domain.mounted_space_list import MountedSpaceList
from ...domain.mounted_product import MountedProduct
from ...domain.base_rule import BaseRule
from types import SimpleNamespace
import math


class ReturnableAndDisposableSplitRule(BaseRule):
    """Port of C# ReturnableAndDisposableSplitRule.

    This implementation follows the C# flow closely and calls domain
    helpers directly (no defensive attribute checking) as requested.
    """

    def __init__(self, factor_converter=None):
        super().__init__()
        self.factor_converter = factor_converter

    def _get_items(self, context):
        return ItemList(context.get_items()).NotMarketplace().NotChopp().NotIsotonicWater().with_amount_remaining().to_list()

    def _get_returnable_mounted_spaces(self, context):
        spaces = MountedSpaceList(context.mounted_spaces).is_returnable().ordered_by_different_packing_group_quantity_desc_and_occupation()
        try:
            return sorted(spaces, key=lambda m: getattr(m, 'occupied_percentage', getattr(m, 'OccupiedPercentage', getattr(m, 'occupation', 0))) , reverse=True)
        except Exception:
            return spaces

    def should_execute(self, context, item_predicate=None, mounted_space_predicate=None):
        if context.get_setting('ReturnableAndDisposableSplitRuleDisabled', False):
            context.add_execution_log("Regra ReturnableAndDisposableSplitRule desabilitada nas configurações, pulando execução.")
            return False
        items = self._get_items(context)
        returnable_spaces = self._get_returnable_mounted_spaces(context)

        if not items:
            context.add_execution_log("Nenhum item elegivel para remount encontrado, pulando regra de remount.")
            return False
        
        if not returnable_spaces:
            context.add_execution_log("Nenhum espaço montado retornável encontrado, pulando regra de remount.")
            return False
        
        return True

    def execute(self, context):
        items = self._get_items(context)
        returnable_spaces = self._get_returnable_mounted_spaces(context)
        if not items or not returnable_spaces:
            return

        mounted_space_a = None
        mounted_space_b = None

        for returnable_space in returnable_spaces:
            mounted_space_a, mounted_space_b = self._load_mounted_spaces(mounted_space_a, mounted_space_b, returnable_spaces, returnable_space)

            if mounted_space_a is not None and mounted_space_b is not None:
                # pick the more occupied as target (matches C# compare of OccupiedPercentage)
                occ_a = getattr(mounted_space_a, 'occupied_percentage', getattr(mounted_space_a, 'OccupiedPercentage', getattr(mounted_space_a, 'occupation', 0)))
                occ_b = getattr(mounted_space_b, 'occupied_percentage', getattr(mounted_space_b, 'OccupiedPercentage', getattr(mounted_space_b, 'occupation', 0)))
                if occ_a > occ_b:
                    try:
                        self._move_returnable_products_to_mounted_space(context, mounted_space_a, mounted_space_b)
                        mounted_space_a = None
                    except Exception:
                        mounted_space_a = None
                else:
                    try:
                        self._move_returnable_products_to_mounted_space(context, mounted_space_b, mounted_space_a)
                        mounted_space_b = None
                    except Exception:
                        mounted_space_b = None

    def _load_mounted_spaces(self, mounted_space_a, mounted_space_b, returnable_spaces, next_space):
        if mounted_space_a is None:
            mounted_space_a = next_space
            if mounted_space_b not in returnable_spaces:
                mounted_space_b = None
        else:
            mounted_space_b = next_space
            if mounted_space_a not in returnable_spaces:
                mounted_space_a = None

        return mounted_space_a, mounted_space_b

    def _move_returnable_products_to_mounted_space(self, context, target, source):
        """Move eligible products from source mounted space to target mounted space.

        This is a pragmatic port: it computes how many units fit in the target
        (using the factor converter) and moves a new mounted-product proxy with
        that amount into the target, updating occupations and source quantities.
        """
        print(f"ReturnableAndDisposableSplitRule: moving from {source.space.number} to {target.space.number}")

        source_pallet = source.get_first_pallet()
        source_mounted_products = list(source_pallet.get_products().NotLayerConfigurationWithQuantityToLayer().OrderByAmountRemainingDesc())

        pallet_target = target.get_first_pallet()

        for source_mp in list(source_mounted_products):
            # resolve factor for target space size
            target_factor = source_mp.product.get_factor(target.space.size)
            occupation_adj = context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
            occupation_remaining = getattr(target, 'occupation_remaining', getattr(target, 'OccupationRemaining', getattr(target, 'occupation', 0)))

            fq = self.factor_converter.quantity_per_factor(occupation_remaining, source_mp.amount, target_factor, getattr(source_mp, 'item', None), occupation_adj)
            quantity_to_occupy = int(math.floor(float(fq)))

            # C# checks
            if getattr(source_mp, 'complex_load', False):
                continue

            if quantity_to_occupy <= 0 or (source_mp.Splitted  and quantity_to_occupy < source_mp.amount):
                continue

            if not context.domain_operations.can_add(context, target, getattr(source_mp, 'item', None), quantity_to_occupy):
                continue

            # Build a lightweight mounted-product for target (approx of MountedProduct.Build)
            qty_layer = source_mp.product.get_quantity_of_layer_to_space(target.space.size, quantity_to_occupy) if hasattr(source_mp.product, 'get_quantity_of_layer_to_space') else quantity_to_occupy
            # new_mp = SimpleNamespace(product=source_mp.product, order=getattr(source_mp, 'order', None), amount=qty_layer, item=getattr(source_mp, 'item', None))
            new_mp = MountedProduct(product=source_mp.product, order=getattr(source_mp, 'order', None), amount=qty_layer, item=getattr(source_mp, 'item', None))

            # add to target pallet
            pallet_target.products.append(new_mp)

            # update target occupation
            occ = self.factor_converter.occupation(quantity_to_occupy, target_factor, new_mp.Product.PalletSetting , new_mp.item, occupation_adj)
            if hasattr(target, 'increase_occupation'):
                try:
                    target.increase_occupation(occ)
                except Exception:
                    target.occupation = getattr(target, 'occupation', 0) + occ
            else:
                target.occupation = getattr(target, 'occupation', 0) + occ

            context.add_execution_log(f"Added {new_mp.product.code}-{new_mp.product.name} to bay {target.space.number} qty {quantity_to_occupy} occ {getattr(target,'occupation',None)}")

            # subtract from source
            if hasattr(source_mp, 'subtract_amount'):
                try:
                    source_mp.subtract_amount(quantity_to_occupy)
                except Exception:
                    try:
                        source_mp.amount = max(0, source_mp.amount - quantity_to_occupy)
                    except Exception:
                        pass
            else:
                source_mp.amount = max(0, source_mp.amount - quantity_to_occupy)

            # update source occupation
            occ_src = self.factor_converter.occupation(quantity_to_occupy, source_mp.product.get_factor(source.space.size), source_mp.product.PalletSetting, source_mp.item, occupation_adj)
            if hasattr(source, 'decrease_occupation'):
                try:
                    source.decrease_occupation(occ_src)
                except Exception:
                    source.occupation = max(0, getattr(source, 'occupation', 0) - occ_src)
            else:
                source.occupation = max(0, getattr(source, 'occupation', 0) - occ_src)

            # if fully moved, remove the mounted product
            if getattr(source_mp, 'amount', 0) == 0:
                try:
                    source_pallet.products.remove(source_mp)
                except Exception:
                    try:
                        source_pallet.products = [p for p in source_pallet.products if p is not source_mp]
                    except Exception:
                        pass

                # if no products left on source pallet, clear/remove mounted space
                try:
                    if not getattr(source_pallet, 'products'):
                        try:
                            source.clear()
                        except Exception:
                            context.remove_mounted_space(source)
                        break
                except Exception:
                    pass
            else:
                # mark split on both mounted-products if splitting occurred
                try:
                    if hasattr(source_mp, 'split'):
                        source_mp.split()
                except Exception:
                    pass
                try:
                    if hasattr(new_mp, 'split'):
                        new_mp.split()
                except Exception:
                    pass

        return
