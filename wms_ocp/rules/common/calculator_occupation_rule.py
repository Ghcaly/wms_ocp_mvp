from decimal import Decimal
from ...domain.base_rule import BaseRule
from ...domain.context import Context
from ...domain.space_size import SpaceSize


class CalculatorOccupationRule(BaseRule):
    def __init__(self, factor_converter=None):
        super().__init__(name='CalculatorOccupationRule')
        self._factor_converter = factor_converter

    def execute(self, context: Context) -> Context:
        # Use provided factor converter or fall back to context/factory
        factor = self._factor_converter or getattr(context, 'factor_converter', None)

        # Mirror the C# loop: foreach order in context.Orders -> foreach item in order.Items
        for order in context.orders:
            for item in order.items:
                # C#: if (!item.Product.Factors.Any(x => x.Size.Equals(SpaceSize.Size42)))
                if not any(getattr(f, 'size', None) == SpaceSize.Size42 for f in (item.product.factors or [])):
                    context.add_execution_log(f"Nenhum produto com tamanho 42 order {getattr(order, 'identifier', getattr(order, 'id', ''))}")
                    continue

                # C#: _factorConverter.Occupation(item.AmountRemaining, SpaceSize.Size42, item, ...)
                occupation_default_per42 = factor.occupation(
                    item.amount_remaining,
                    Decimal(SpaceSize.Size42),
                    item,
                    context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
                )

                item.SetOcpDefaultPerUni42(occupation_default_per42)

        return context
