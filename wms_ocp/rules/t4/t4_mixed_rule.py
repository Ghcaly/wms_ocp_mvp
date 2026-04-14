import logging
from ...domain.base_rule import BaseRule
from ...domain.context import Context


class T4MixedRule(BaseRule):
    def __init__(self, mixed_rules_factory=None, bays_needed_rule=None, number_of_pallets_rule=None):
        self.mixed_rules_factory = mixed_rules_factory
        self.bays_needed_rule = bays_needed_rule
        self.number_of_pallets_rule = number_of_pallets_rule
        self.logger = logging.getLogger(__name__)

    def should_execute(self, context: Context, item_predicate=None, mounted_space_predicate=None) -> bool:
        any_order = bool(context.orders)
        if not any_order:
            self.logger.debug('Nenhuma ordem para executar')
            return False
        return True

    def execute(self, context: Context) -> Context:
        self.logger.debug('Paletizando os itens')

        orders = list(context.orders)
        new_context = context

        for order in orders:
            old_sum_of_amount = 1
            sum_of_amount = 0
            attempt = 0
            retries = 0

            while self._has_space_and_not_palletized_items(new_context, order) and old_sum_of_amount != sum_of_amount:
                self.logger.debug(f'Loop Mixed Rule nº {retries}')

                # C#: var rules = _mixedRulesFactory.CreateRulesChain(newContext.Settings)
                rules = None
                if self.mixed_rules_factory and hasattr(self.mixed_rules_factory, 'create_rules_chain'):
                    settings = getattr(new_context, 'settings', getattr(new_context, 'Settings', None))
                    rules = self.mixed_rules_factory.create_rules_chain(settings)

                new_context.clear_filters()
                if not getattr(new_context, 'spaces', []):
                    break

                old_sum_of_amount = sum(
                    getattr(x, 'amount_remaining', getattr(x, 'AmountRemaining', 0))
                    for x in order.get_items_palletizable()
                )

                order.set_additional_spaces(attempt)
                new_context.with_only_order(order)

                if self.number_of_pallets_rule:
                    new_context = self.number_of_pallets_rule.execute_chain(new_context)
                if self.bays_needed_rule:
                    new_context = self.bays_needed_rule.execute_chain(new_context)
                if rules:
                    new_context = rules.execute_chain(new_context)

                new_context.clear_filters()

                sum_of_amount = sum(
                    getattr(x, 'amount_remaining', getattr(x, 'AmountRemaining', 0))
                    for x in order.get_items_palletizable()
                )

                attempt += 1
                retries += 1

        return new_context

    def _has_space_and_not_palletized_items(self, context: Context, order) -> bool:
        # C#: context.Spaces.Count >= 1 && context.GetItemsPalletizableByOrder(order).WithAmountRemaining().Any()
        spaces = getattr(context, 'spaces', [])
        if len(spaces) < 1:
            return False
        if hasattr(context, 'get_items_palletizable_by_order'):
            items = context.get_items_palletizable_by_order(order)
        else:
            items = order.get_items_palletizable()
        return any(getattr(i, 'amount_remaining', getattr(i, 'AmountRemaining', 0)) > 0 for i in items)
