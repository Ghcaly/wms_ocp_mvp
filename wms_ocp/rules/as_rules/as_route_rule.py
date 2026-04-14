from typing import Any
import logging

from ...domain.base_rule import BaseRule
from ...domain.context import Context
from ...factories.route_rule_principal_factories import RouteRulePrincipalFactories


class ASRouteRule(BaseRule):
    def __init__(self):
        super().__init__()
        self.route_rules_chain = RouteRulePrincipalFactories().create_principal_route_chain()
        self.logger = logging.getLogger(__name__)

    def execute(self, context: Context) -> Context:
        # Iterate over a copy of orders and execute route chain for each
        orders = list(context.orders)
        new_context = context
        total = len(orders)
        for idx, order in enumerate(orders, start=1):
            remaining = total - idx
            if remaining<=2:
                print("Faltam menos de 2 orderns")
            self.logger.debug(f"Processing order {idx}/{total} — remaining: {remaining}")
            if self.route_rules_chain:
                new_context.with_only_order(order)
                new_context = self.route_rules_chain.execute_chain(new_context)

        # If not mixed or crossdocking contexts, clear filters
        # if not getattr(context, 'is_mixed', False) and not getattr(context, 'is_crossdocking', False):
        if context.Kind not in ('CrossDocking', 'Mixed'):
            new_context.clear_filters()

        return new_context
