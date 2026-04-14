from ...domain.product import DisposableProduct
from ...domain.itemList import ItemList
from ...domain.base_rule import BaseRule
import math
from typing import List


class LayerRule(BaseRule):
    """Python port of the C# LayerRule.

    This version intentionally calls attributes and methods directly (no
    defensive existence checks) to remain concise and faithful to the C# logic.
    """

    SPACE_SIZE_CHAIN = [42, 35, 28, 21, 14]

    def __init__(self, factor_converter = None):
        super().__init__()
        self.factor_converter = factor_converter

    def execute(self, context):
        try:
            items = (ItemList(context.get_items())
                .not_marketplace()
                .with_layer_code()
                .with_amount_remaining()
            )
            
            bays = context.domain_operations.ordered_by(context.get_not_full_spaces(), fields=["size", "number"])

            # for item in context.domain_operations.ordered_by(items, fields=["priority", "amount_remaining"]):
            for item in context.domain_operations.ordered_by(items, fields=["priority", "amount_remaining"]):
                # similar_products = context.domain_operations.ordered_by(
                #         ItemList(items).layer_code(item.product.LayerCode).isDisposable()
                #         ,fields= [("layers_remaining", "desc")]
                # )   

                similar_products = (
                    ItemList(items)
                    .matching(lambda x: x.Product.LayerCode == item.Product.LayerCode)  # Filtro
                    .OrderBy(lambda x: isinstance(x.Product, DisposableProduct))        # Non-Disposable primeiro
                    .ThenByDescending(lambda x: x.layers_remaining)                      # Layers maior primeiro
                )                

                # if len(similar_products) > 0:
                #     print(f"No similar products found for item {item.code} with layer code {item.Product.LayerCode}")

                self._process_size_chains(context, bays, item, similar_products)
        except Exception as e:
            print(f"Error executing LayerRule: {e}")
            
    def _process_size_chains(self, context, bays: List, item, similar_products):
        # emulate SpaceSizeExtensions.SpaceSizeChains()
        size_chains = []
        for i, s in enumerate(self.SPACE_SIZE_CHAIN):
            nxt = self.SPACE_SIZE_CHAIN[i + 1] if i + 1 < len(self.SPACE_SIZE_CHAIN) else None
            size_chains.append({'current': s, 'next': nxt})

        for size in size_chains:
            for bay in [b for b in bays if b.size == size['current']]:
                self._process_similar_products(context, bays, bay, item, similar_products, size)

    def _process_similar_products(self, context, bays: List, space, item, similar_products, size):
        for similar in [p for p in similar_products if p.amount_remaining > 0]:
            mounted_bay = context.get_mounted_space(space)
            factor = similar.Product.get_factor(space.size)
            pallet_settings = similar.Product.PalletSetting

            current_occupation = mounted_bay.occupation if mounted_bay is not None else 0
            free_occupation = int(space.size) - current_occupation

            quantity = int(math.floor(self.factor_converter.quantity_per_factor(free_occupation, similar.amount_remaining, factor, similar, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))))
            ballast = int(math.floor(quantity / pallet_settings.QuantityBallast))

            if quantity <= 0 or ballast <= 0:
                continue

            if similar.amount_remaining - ballast * pallet_settings.QuantityBallast >= pallet_settings.QuantityBallast and current_occupation > 0:
                continue

            if ballast < pallet_settings.QuantityBallastMin:
                similar.Product.set_layer_code(0)
                continue

            quantity = ballast * pallet_settings.QuantityBallast

            boxes = self.factor_converter.occupation(quantity, factor, pallet_settings, similar, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))

            if space.size < current_occupation + boxes:
                continue

            if mounted_bay is None or not context.domain_operations.can_add_basic(context, mounted_bay, similar):
                continue

            if self._next_space_size_has_free_space(bays, size, similar, ballast, boxes, context.get_setting('OccupationAdjustmentToPreventExcessHeight')):
                continue

            occupation = int(math.floor(boxes))
            quantity_of_layer = int(quantity / ballast)
            first_layer = 0

            context.add_product(space, item, quantity, first_layer, quantity_of_layer, occupation)

    def _next_space_size_has_free_space(self, bays: List, size, similar_product, ballast, boxes, calculate_additional_occupation):
        pallet_setting = similar_product.Product.PalletSetting
        if size['next'] is None or not any(p.size == size['next'] for p in bays) or ballast >= similar_product.Product.PalletSetting.layers:
            return False

        boxes_occupation = boxes * 100 / size['current']
        factor_of_next = similar_product.Product.get_factor(size['next'])
        quantity_of_next = int(math.floor(self.factor_converter.quantity_per_factor(size['next'], similar_product.amount_remaining, factor_of_next, similar_product, calculate_additional_occupation)))

        ballast_of_next = int(math.floor(quantity_of_next / pallet_setting.quantity_ballast))
        quantity_of_next = ballast_of_next * pallet_setting.quantity_ballast

        boxes_of_next = self.factor_converter.occupation(quantity_of_next, factor_of_next, pallet_setting, similar_product, calculate_additional_occupation)
        boxes_occupation_of_next = boxes_of_next * 100 / size['next']

        return boxes_of_next <= size['next'] and boxes_occupation_of_next > boxes_occupation


