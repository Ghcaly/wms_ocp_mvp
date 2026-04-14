import logging
from ...domain.context import Context
from ...domain.calculator_constants import CalculatorConstants
from .cross_base_rule import CrossBaseRule

class JoinMapsRule(CrossBaseRule):
    def __init__(self, factor_converter=None):
        super().__init__()
        self.factor_converter = factor_converter

    def execute(self, context: Context) -> Context:
        new_context = context

        # maps = newContext.GetItems().WithAmountRemaining().Select(x => x.MapNumber).Distinct();
        maps = set(x.MapNumber for x in new_context.GetItems().WithAmountRemaining())

        retries = 0
        for map_number in maps:
            has_not_palletized_items = True
            while has_not_palletized_items and (new_context.Spaces.Any() or self._join_first_maps_with_same_plate(new_context)) and retries <= CalculatorConstants.NUMBER_OF_MAX_RETRIES:
                self.logger.debug(f'Loop AS Rule nº {retries}')

                new_context = self.execute_as_rules(new_context, map_number)

                has_not_palletized_items = any(x.MapNumber == map_number for x in new_context.GetItems().WithAmountRemaining())
                retries += 1

        # propagate changes to original context (C# ChangeContext)
        self._change_context(context, new_context)
        return context

    def _join_first_maps_with_same_plate(self, context: Context) -> bool:
        plates = context.MountedSpaces.GetCrossPlates()

        for plate in plates:
            orders = [o for o in context.Orders if all(y.LicensePlate == plate for y in o.Items)]
            mounted_spaces = [m for m in context.MountedSpaces if m.Order in orders]
            mounted_spaces = sorted(mounted_spaces, key=lambda x: x.Occupation)[:2]
            if len(mounted_spaces) <= 1:
                continue

            first_mounted_space = mounted_spaces[0]

            # Collect all products and compute total occupation using factor_converter (C# parity)
            all_products = [p for m in mounted_spaces for p in m.GetProducts()]
            if self.factor_converter and all_products:
                total_occupation = sum(self.factor_converter.Occupation(p.Amount, first_mounted_space.Space.Size, next(y for y in p.Order.Items if y.Product == p.Product), context.Settings.OccupationAdjustmentToPreventExcessHeight) for p in all_products)
            else:
                total_occupation = sum(p.EstimatedOccupation for p in all_products)

            if total_occupation > int(first_mounted_space.Space.Size):
                continue

            second_mounted_space = mounted_spaces[-1]
            self.logger.debug(f'Juntando o espaco {second_mounted_space.Space.Number}/{getattr(second_mounted_space.Space, "Side", "?")} no {first_mounted_space.Space.Number}/{getattr(first_mounted_space.Space, "Side", "?")}', extra={'context': context})

            context.SwitchProducts(first_mounted_space, second_mounted_space, total_occupation)
            context.RemoveMountedSpace(second_mounted_space)

            return True

        return False
