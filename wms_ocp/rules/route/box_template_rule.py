from ...domain.itemList import ItemList
from ...domain.space_list import SpaceList
from ...domain.base_rule import BaseRule
from ...domain.factor_converter import FactorConverter
import math


class BoxTemplateRule(BaseRule):
    """Direct port of C# BoxTemplateRule.

    Calls methods/attributes exactly as in the original C# (no defensive
    existence checks) to remain faithful to behavior and names.
    """

    def __init__(self, factor_converter: FactorConverter = None):
        super().__init__(name='BoxTemplateRule')
        self._factor_converter = factor_converter or FactorConverter()

    def should_execute(self, context, item_predicate=None, mounted_space_predicate=None):
        items = ItemList(context.get_items()).is_box_template().with_amount_remaining().ordered_by_amount_remaining_desc()
        if not items:
            context.add_execution_log(f"Motivo - Nao foram encontrados items BoxTemplate para paletizar")
            return False
    
        available_spaces = SpaceList(context.get_not_full_spaces()).OrderedByPackageThenBoxTemplateThenOccupation(context)
        
        if not any(available_spaces):
            context.add_execution_log(f"Motivo - Nao foram encontradas baias com espaço disponível para paletizar os itens BoxTemplate")
            return False

        return True
        

    def execute(self, context):
        print("Iniciando execução da regra")
        items = ItemList(context.get_items()).is_box_template().with_amount_remaining().ordered_by_amount_remaining_desc()
        avaliableSpaces = SpaceList(context.get_not_full_spaces()).OrderedByPackageThenBoxTemplateThenOccupation(context)

        for item in items:
            for space in avaliableSpaces:
                if item.amount_remaining <= 0:
                    print(f"O item {item.code} foi paletizado completamente")
                    break

                mountedSpace = context.get_mounted_space(space)
                occupationRemaining = space.size if mountedSpace is None else mountedSpace.occupation_remaining

                quantity = int(math.floor(self._factor_converter.quantity_per_factor(
                    occupationRemaining,
                    item.amount_remaining,
                    item.product.get_factor(space.size),
                    item,
                    context.get_setting('OccupationAdjustmentToPreventExcessHeight', False),
                )))

                if quantity < 1:
                    context.add_execution_log(f"O item BoxTemplate: {item.Code} não cabe na baia: {space.Number}/{getattr(space, 'Side', getattr(space, 'side', '?'))}")
                    continue

                if not context.domain_operations.can_add(context, space, item, quantity):
                    continue

                firstLayer = mountedSpace.get_next_layer() if mountedSpace is not None else 0
                quantityOfLayer = item.product.get_quantity_of_layer_to_space(space.size, quantity)
                occupation = self._factor_converter.occupation(quantity, space.size, item, context.get_setting('OccupationAdjustmentToPreventExcessHeight', False))

                context.add_execution_log(f"Paletizando o item: {item.Code} na quantidade: {quantity} na baia: {space.number}/{space.sideDesc} e ocupação: {occupation}")
                context.AddProduct(space, item, quantity, firstLayer, quantityOfLayer, occupation, item.amount_remaining)
