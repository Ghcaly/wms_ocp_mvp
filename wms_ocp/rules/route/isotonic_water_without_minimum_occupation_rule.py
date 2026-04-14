from ...domain.itemList import ItemList
from .isotonic_water_rule import IsotonicWaterRule
from .non_layer_on_layer_pallet_rule import NonLayerOnLayerPalletRule
from .returnable_and_disposable_split_remount_rule import ReturnableAndDisposableSplitRemountRule
from .returnable_and_disposable_split_rule import ReturnableAndDisposableSplitRule
from ...domain.base_rule import BaseRule
from ...domain.context import Context

class IsotonicWaterWithoutMinimumOccupationRule(BaseRule):
    def __init__(self, isotonic_rule=None, returnable_split_rule=None, non_layer_rule=None, returnable_split_remount_rule=None):
        self.isotonic_rule = isotonic_rule or IsotonicWaterRule()
        self.returnable_split_rule = returnable_split_rule or ReturnableAndDisposableSplitRule()
        self.non_layer_rule = non_layer_rule or NonLayerOnLayerPalletRule()
        self.returnable_split_remount_rule = returnable_split_remount_rule or ReturnableAndDisposableSplitRemountRule()

    def execute(self, context: Context):
        # 1) run isotonic rule's WithoutMinOccupationValidation
        if self.isotonic_rule:
            try:
                iso = self.isotonic_rule.WithoutMinOccupationValidation()
                iso.execute(context)
            except Exception as e:
                print(f"Error in isotonic_water_rule: {e}")
                pass

        # 2) if there are isotonic-water items remaining, run isotonic rule again
        items = context.get_items()
        isotonic_remaining = ItemList(items).not_marketplace().is_isotonic_water().with_amount_remaining()
        if isotonic_remaining and self.isotonic_rule:
            try:
                iso = self.isotonic_rule.WithoutMinOccupationValidation()
                iso.execute(context)
            except Exception as e:
                print(f"Error in isotonic_water_rule: {e}")
                pass

        # 3) optionally adjust reassembles after water: run returnable/disposable split rules
        try:
            adjust = context.get_setting('AdjustReassemblesAfterWater', False)
        except Exception:
            adjust = False

        if adjust:
            try:
                remaining_for_split = ItemList(items).not_marketplace().not_chopp().with_amount_remaining()
                if remaining_for_split and self.returnable_split_rule:
                    self.returnable_split_rule.execute(context)

                if self.returnable_split_remount_rule:
                    # pass an item predicate as in C# (items => NotMarketplace && NotChopp && HasAmountRemaining)
                    item_pred = lambda it: (not it.is_marketplace) and (not it.is_chopp) and (getattr(it, 'amount_remaining', 0) > 0)
                    self.returnable_split_remount_rule.execute(context, item_pred)
            except Exception as e:
                print(f"Error in returnable_split_remount_rule: {e}")
                pass

        # 4) if there are layer mounted spaces and non-chopp items remaining, run non-layer-on-layer rule
        try:
            has_layer = any(ms.HasLayer() for ms in context.mounted_spaces)
        except Exception as e:
            print(f"Error in non_layer_on_layer_pallet_rule: {e}")
            has_layer = False

        non_chopp_remaining = any(i.amount_remaining > 0 and not i.is_chopp for i in context.get_items())
        if has_layer and non_chopp_remaining and self.non_layer_rule:
            try:
                item_pred = lambda it: (not it.is_chopp) and (not it.is_marketplace) and (getattr(it, 'amount_remaining', 0) > 0)
                mounted_pred = lambda msp: getattr(msp, 'is_layer', False)
                self.non_layer_rule.execute(context, item_pred, mounted_pred)
            except Exception as e:
                print(f"Error in non_layer_on_layer_pallet_rule: {e}")
                pass
