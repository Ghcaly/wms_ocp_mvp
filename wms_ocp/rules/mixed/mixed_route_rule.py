import logging
from ...domain.base_rule import BaseRule
from ...domain.context import Context, T4RuleContext


class MixedRouteRule(BaseRule):
    def __init__(self, route_rules_factory=None, bays_needed_rule=None, number_of_pallets_rule=None):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.route_rules_factory = route_rules_factory
        self.bays_needed_rule = bays_needed_rule
        self.number_of_pallets_rule = number_of_pallets_rule

    def _get_route_order(self, context: Context):
        return next((o for o in context.orders if any(getattr(i, 'customer', '') == '' for i in o.items)), None)

    def should_execute(self, context: Context) -> bool:
        order = self._get_route_order(context)
        if order is None:
            self.logger.debug('Nenhuma ordem de Rota para executar')
            return False
        return True

    def execute(self, context: Context) -> Context:
        self.logger.debug('Paletizando itens Rota')
        new_context = context
        route_order = self._get_route_order(context)

        old_sum_of_amount = 1
        sum_of_amount = 0
        retries = 0

        while old_sum_of_amount != sum_of_amount:
            self.logger.debug(f'Loop Mixed Route Rule nº {retries}')

            route_rules = None
            if self.route_rules_factory and hasattr(self.route_rules_factory, 'create_rules_chain'):
                route_rules = self.route_rules_factory.create_rules_chain(new_context.settings)
            elif hasattr(context, 'service') and context.service:
                route_rules = context.service.create_rules_chain({'chain_type': 'route', 'context': context})

            new_context.clear_filters()
            if not new_context.spaces:
                break

            old_sum_of_amount = sum(getattr(x, 'amount_remaining', 0) for x in route_order.get_items_palletizable()) if route_order else 0

            # C#: if (context is not IT4RuleContext)
            if not isinstance(context, T4RuleContext):
                if hasattr(route_order, 'set_additional_spaces'):
                    route_order.set_additional_spaces(len(new_context.spaces))

            new_context.with_only_order(route_order)

            if self.number_of_pallets_rule and hasattr(self.number_of_pallets_rule, 'execute_chain'):
                new_context = self.number_of_pallets_rule.execute_chain(new_context)
            if self.bays_needed_rule and hasattr(self.bays_needed_rule, 'execute_chain'):
                new_context = self.bays_needed_rule.execute_chain(new_context)

            if route_rules:
                new_context = route_rules.execute_chain(new_context)

            new_context.clear_filters()

            sum_of_amount = sum(getattr(x, 'amount_remaining', 0) for x in route_order.get_items_palletizable()) if route_order else 0

            retries += 1

        new_context.clear_filters()
        return new_context
