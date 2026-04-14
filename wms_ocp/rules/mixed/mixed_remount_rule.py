import logging
from ...domain.base_rule import BaseRule
from ...domain.context import Context


class MixedRemountRule(BaseRule):
    def __init__(self, route_rules_factory=None):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.route_rules_factory = route_rules_factory

    def _get_route_order(self, context: Context):
        return next((o for o in context.orders if any(getattr(i, 'customer', '') == '' for i in o.items)), None)

    def should_execute(self, context: Context) -> bool:
        order = self._get_route_order(context)
        has_not_palletized = any(i.amount_remaining for i in (order.get_items_palletizable() if order else []))
        if order is None or not has_not_palletized or not getattr(context, 'mounted_spaces', []):
            self.logger.debug('Nenhum item para gerar remonte')
            return False
        return True

    def execute(self, context: Context) -> Context:
        self.logger.debug('Paletizando itens com remonte')

        if getattr(context, 'settings', {}).get('MaxPackageGroups', 0) < 2:
            context.domain_operations.with_max_groups(2)

        new_context = self._palletize_remount(context)
        new_context = self._create_remount(new_context)

        context.domain_operations.with_max_groups(None)

        return new_context

    def _create_remount(self, context: Context) -> Context:
        if not any(getattr(i, 'amount_remaining', 0) for i in context.get_items()):
            return context

        new_context = context
        old_sum_of_amount = 1
        sum_of_amount = 0
        retries = 0

        while old_sum_of_amount != sum_of_amount:
            self.logger.debug(f'Loop Mixed Remount Rule nº {retries}')

            old_sum_of_amount = sum(getattr(i, 'amount_remaining', 0) for i in context.get_items())
            if old_sum_of_amount == 0:
                break

            self._join_mounted_spaces(context)

            new_context = self._palletize_remount(context)

            sum_of_amount = sum(getattr(i, 'amount_remaining', 0) for i in context.get_items())
            if sum_of_amount == 0:
                break

            retries += 1

        return new_context

    def _join_mounted_spaces(self, context: Context):
        mounted_spaces = sorted(getattr(context, 'mounted_spaces', []), key=lambda x: getattr(x, 'occupation', 0))
        for first in mounted_spaces:
            for second in [m for m in mounted_spaces if m.order == first.order]:
                if first == second:
                    continue

                if not context.domain_operations.can_add(context, second, first):
                    continue

                # C#: if (switchSucceeded) firstMountedSpace.RemoveContainers()
                switch_succeeded = context.domain_operations.change_product_full_space(context, second, first)
                if switch_succeeded and hasattr(first, 'remove_containers'):
                    first.remove_containers()
                return

    def _palletize_remount(self, context: Context) -> Context:
        route_order = self._get_route_order(context)
        new_context = context

        route_rules = None
        if self.route_rules_factory and hasattr(self.route_rules_factory, 'create_rules_chain'):
            route_rules = self.route_rules_factory.create_rules_chain(new_context.settings)
        elif hasattr(context, 'service') and context.service:
            route_rules = context.service.create_rules_chain({'chain_type': 'route', 'context': context})

        old_sum_of_amount = 1
        sum_of_amount = 0
        retries = 0

        while old_sum_of_amount != sum_of_amount:
            self.logger.debug(f'Loop Mixed Remount Rule nº {retries}')

            old_sum_of_amount = sum(getattr(x, 'amount_remaining', 0) for x in route_order.get_items_palletizable()) if route_order else 0
            if old_sum_of_amount == 0:
                break

            mounted_spaces = [m for m in new_context.mounted_spaces if (m.order == route_order or m.order is None)]
            mounted_spaces = [m for m in mounted_spaces if not getattr(m, 'is_bulk', False)]
            mounted_spaces = sorted(mounted_spaces, key=lambda x: getattr(x, 'occupation', 0))

            if getattr(new_context, 'settings', {}).get('KegExclusivePallet'):
                mounted_spaces = [m for m in mounted_spaces if not getattr(m, 'is_chopp', False)]

            if not mounted_spaces:
                break

            for mounted_space in mounted_spaces:
                # Filter
                new_context.with_only_order(route_order)
                if getattr(mounted_space, 'order', None) is None:
                    self.logger.debug('Using space filter')
                    new_context.with_only_space(mounted_space.space if hasattr(mounted_space, 'space') else mounted_space)
                else:
                    self.logger.debug('Using mountedSpace filter')
                    new_context.with_only_mounted_space(mounted_space)

                if route_rules:
                    new_context = route_rules.execute_chain(new_context)

                new_context.clear_filters()

                sum_of_amount = sum(getattr(x, 'amount_remaining', 0) for x in route_order.get_items_palletizable()) if route_order else 0

                if sum_of_amount == 0:
                    break

            retries += 1

        new_context.clear_filters()
        return new_context
