from ...domain.base_rule import BaseRule
from ...domain.context import Context
from ...domain.calculator_constants import CalculatorConstants
from typing import List
from decimal import Decimal


class BaysNeededRule(BaseRule):

    def __init__(self):
        pass

    def execute(self, context: Context):
        amountBaysNeededToMap = self.get_amount_bays_needed_to_map(context)
        self.update_amount_bays_needed_by_order(context)
        self.update_amount_bays_needed_rounded_by_order(context, amountBaysNeededToMap)

    def get_amount_bays_needed_to_map(self, context: Context) -> Decimal:
        amount_bays_needed_to_map = sum(order.quantity_of_pallets_needed for order in context.orders)
        amount_bays_needed_without_fractional = int(amount_bays_needed_to_map)
        fractional_amount_bays_needed_to_map = amount_bays_needed_to_map - amount_bays_needed_without_fractional
        if (fractional_amount_bays_needed_to_map > CalculatorConstants.MAXIMUM_FRACTIONAL_VALUE_TO_ROUND
                and fractional_amount_bays_needed_to_map < CalculatorConstants.MINIMUM_FRACTIONAL_VALUE_TO_ROUND):
            return amount_bays_needed_to_map
        else:
            return self.round_to_upper(amount_bays_needed_to_map)

    def update_amount_bays_needed_by_order(self, context: Context):
        for order in context.orders:
            fractional = order.quantity_of_pallets_needed - int(order.quantity_of_pallets_needed)
            if (fractional <= CalculatorConstants.MAXIMUM_FRACTIONAL_VALUE_TO_ROUND
                    or fractional >= CalculatorConstants.MINIMUM_FRACTIONAL_VALUE_TO_ROUND):
                order.set_quantity_of_pallets_needed(self.round_to_upper(order.quantity_of_pallets_needed))

    def update_amount_bays_needed_rounded_by_order(self, context: Context, amount_bays_needed_to_map: Decimal):
        self.set_amount_rounded_to_upper(context)
        self.adjust_amount_rounded_to_fit(context, amount_bays_needed_to_map)

    def set_amount_rounded_to_upper(self, context: Context):
        for order in context.orders:
            quantity_of_pallets_needed_rounded = self.round_to_upper(order.quantity_of_pallets_needed)
            order.set_quantity_of_pallets_needed_rounded(quantity_of_pallets_needed_rounded)

    def adjust_amount_rounded_to_fit(self, context: Context, amount_bays_needed_to_map: Decimal):
        # C#: amountEmptyBaysLeft = (int)(context.Spaces.Count - amountBaysNeededToMap)
        spaces_count = len(getattr(context, 'spaces', []))
        amount_empty_bays_left = int(spaces_count - amount_bays_needed_to_map)

        current_amount_bays_needed_rounded = sum(
            getattr(order, 'quantity_of_pallets_needed_rounded', self.round_to_upper(order.quantity_of_pallets_needed))
            for order in context.orders
        )

        # C#: if (currentAmountBaysNeededRounded <= context.Spaces.Count) return;
        if current_amount_bays_needed_rounded <= spaces_count:
            return

        # C#: if (amountEmptyBaysLeft < 1) return;
        if amount_empty_bays_left < 1:
            return

        # C#: foreach order - reduce by 1 until amountEmptyBaysLeft == 0
        for order in context.orders:
            quantity_reduced = getattr(order, 'quantity_of_pallets_needed_rounded',
                                       self.round_to_upper(order.quantity_of_pallets_needed)) - 1
            order.set_quantity_of_pallets_needed_rounded(quantity_reduced)
            amount_empty_bays_left -= 1
            if amount_empty_bays_left == 0:
                break

    @staticmethod
    def round_to_upper(value: Decimal) -> Decimal:
        return Decimal(int(value) + (1 if value % 1 > 0 else 0))
