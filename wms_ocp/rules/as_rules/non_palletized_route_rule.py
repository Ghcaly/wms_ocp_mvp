import logging
from ...domain.base_rule import BaseRule
from ...domain.context import Context
from ...factories.route_rule_factories import RouteRuleFactories


class NonPalletizedRouteRule(BaseRule):
    def __init__(self):
        super().__init__()
        self.route_rules_factory = RouteRuleFactories()
        self.logger = logging.getLogger(__name__)

    def should_execute(self, context: Context, item_predicate=None, mounted_space_predicate=None) -> bool:
        if getattr(context, 'spaces', None) and len(context.spaces) > 0:
            return True
        self.logger.debug('Nenhum espaco vazio para paletizar, finalizando a execucao da regra')
        return False

    def execute(self, context: Context) -> Context:
        self.logger.debug('Iniciando execucao da regra NonPalletizedRouteRule')

        new_context = context
        empty_spaces = list(getattr(new_context, 'spaces', []))
        orders = list(getattr(new_context, 'orders', []))

        for space in empty_spaces:
            for order in orders:
                if not any(getattr(i, 'can_be_palletized', False) and getattr(i, 'amount_remaining', 0) > 0
                           for i in getattr(order, 'items', [])):
                    continue

                self.logger.debug(f'Paletizando o espaco vazio {getattr(space, "number", "?")}/{getattr(space, "side", "?")} com os itens da ordem {getattr(order, "delivery_order", "?")}')

                # C#: var rules = _routeRuleFactory.CreateRulesChain(newContext.Settings)
                route_rules_chain = self.route_rules_factory.create_route_chain()
                if route_rules_chain:
                    new_context.with_only_order(order)
                    new_context.with_only_space(space)
                    new_context = route_rules_chain.execute_chain(new_context)
                    new_context.clear_filters()

        return new_context
