import logging
from ...domain.context import Context
from ...domain.calculator_constants import CalculatorConstants
from .cross_base_rule import CrossBaseRule


class JoinPlatesRule(CrossBaseRule):
    def __init__(self, factor_converter=None):
        super().__init__()
        self.factor_converter = factor_converter

    def execute(self, context: Context) -> Context:
        # faithful port of C#: use PascalCase calls/attributes directly
        new_context = context

        plates = set(x.LicensePlate for x in new_context.GetItems().WithAmountRemaining())

        retries = 0
        for plate in plates:
            has_not_palletized_items = True
            while has_not_palletized_items and (new_context.Spaces.Any() or self._join_first_maps(new_context)) and retries < CalculatorConstants.NUMBER_OF_MAX_RETRIES:
                self.logger.debug(f'Loop AS Rule nº {retries}')
                new_context = self.execute_as_rules(new_context, plate)
                has_not_palletized_items = any(x.LicensePlate == plate for x in new_context.GetItems().WithAmountRemaining())
                retries += 1

        # propagate changes back to original context (C# ChangeContext(newContext))
        self._change_context(context, new_context)
        return context

    def _join_first_maps(self, context: Context) -> bool:
        mounted_spaces = sorted(context.MountedSpaces, key=lambda x: x.Occupation)[:2]
        if len(mounted_spaces) <= 1:
            return False

        first_mounted_space = mounted_spaces[0]
        all_products = [p for m in mounted_spaces for p in m.GetProducts()]

        if self.factor_converter and all_products:
            total_occupation = sum(
                self.factor_converter.Occupation(
                    p.Amount,
                    first_mounted_space.Space.Size,
                    next(y for y in p.Order.Items if y.Product == p.Product),
                    context.Settings.OccupationAdjustmentToPreventExcessHeight,
                )
                for p in all_products
            )
        else:
            total_occupation = sum(p.EstimatedOccupation for p in all_products)

        if total_occupation > int(first_mounted_space.Space.Size):
            return False

        second_mounted_space = mounted_spaces[-1]

        self.logger.debug(
            f'Juntando o espaco {second_mounted_space.Space.Number}/{getattr(second_mounted_space.Space, "Side", "?")} '
            f'no {first_mounted_space.Space.Number}/{getattr(first_mounted_space.Space, "Side", "?")}',
            extra={'context': context},
        )

        context.SwitchProducts(first_mounted_space, second_mounted_space, total_occupation)
        context.RemoveMountedSpace(second_mounted_space)

        return True

    def _change_context(self, original_context: Context, new_context: Context):
        """Apply snapshot/new_context changes into original_context (parity with C# ChangeContext)."""
        original_context.Orders = new_context.Orders
        original_context.Spaces = new_context.Spaces
        original_context.MountedSpaces = new_context.MountedSpaces

