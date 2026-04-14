import logging

from ...domain.base_rule import BaseRule
from ...domain.context import Context, MixedRuleContext, CrossDockingRuleContext
from ...factories.route_rule_factories import RouteRuleFactories


class ASRouteRule(BaseRule):
    def __init__(self):
        super().__init__()
        self.route_rules_factory = RouteRuleFactories()
        self.logger = logging.getLogger(__name__)

    def execute(self, context: Context) -> Context:
        orders = list(context.orders)
        new_context = context
        for order in orders:
            # C#: var rules = _routeRuleFactory.CreateRulesChain(newContext.Settings)
            route_rules_chain = self.route_rules_factory.create_route_chain()
            if route_rules_chain:
                new_context.with_only_order(order)
                new_context = route_rules_chain.execute_chain(new_context)

        # C#: if (context is not IMixedRuleContext && context is not ICrossDockingRuleContext)
        if not isinstance(context, MixedRuleContext) and not isinstance(context, CrossDockingRuleContext):
            new_context.clear_filters()

        return new_context
