import logging
from ...domain.base_rule import BaseRule
from ...domain.context import Context


class MixedASRule(BaseRule):
    def __init__(self, as_rules_factory=None):
        super().__init__()
        self.as_rules_factory = as_rules_factory
        self.logger = logging.getLogger(__name__)

    def _get_orders(self, context: Context):
        return [
            o for o in context.orders
            if any(
                getattr(i, 'customer', None) not in (None, '')
                for i in o.items
            )
        ]

    def should_execute(self, context: Context) -> bool:
        any_order = bool(self._get_orders(context))
        if not any_order:
            self.logger.debug('Nenhuma ordem de AS para executar')
            return False
        return True

    def execute(self, context: Context) -> Context:
        self.logger.debug('Paletizando itens AS')
        as_orders = self._get_orders(context)
        new_context = context

        for order in as_orders:
            old_sum = 1
            sum_of_amount = 0
            attempt = 0
            retries = 0

            while (len(new_context.spaces) >= 1 and any(i.amount_remaining for i in order.get_items_palletizable())) and old_sum != sum_of_amount:
                self.logger.debug(f'Loop Mixed AS Rule nº {retries}')

                if hasattr(order, 'set_additional_spaces'):
                    order.set_additional_spaces(attempt)

                old_sum = sum(getattr(x, 'amount_remaining', 0) for x in order.get_items_palletizable())
                rules = None
                if self.as_rules_factory and hasattr(self.as_rules_factory, 'create_rules_chain'):
                    rules = self.as_rules_factory.create_rules_chain(new_context.settings)
                elif hasattr(context, 'service') and context.service:
                    rules = context.service.create_rules_chain({'chain_type': 'as', 'context': context})

                new_context.with_only_order(order)
                if rules:
                    new_context = rules.execute_chain(new_context)
                new_context.clear_filters()
                sum_of_amount = sum(getattr(x, 'amount_remaining', 0) for x in order.get_items_palletizable())
                attempt += 1
                retries += 1

        return new_context
