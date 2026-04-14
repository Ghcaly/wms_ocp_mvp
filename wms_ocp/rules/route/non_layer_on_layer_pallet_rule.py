from ...domain.base_rule import BaseRule
from ...domain.itemList import ItemList
from ...domain.mounted_space_list import MountedSpaceList
from ...domain.product import ContainerType


class NonLayerOnLayerPalletRule(BaseRule):
    """Faithful port of C# NonLayerOnLayerPalletRule.

    Calls methods directly (no defensive guards) to remain concise and
    behave like the original C# implementation.
    """

    def __init__(self, factor_converter=None, mounted_space_operations=None, context_actions=None):
        super().__init__()
        self.factor_converter = factor_converter
        self.mounted_space_operations = mounted_space_operations
        self.context_actions = context_actions

    def should_execute(self, context, item_predicate=None, mounted_space_predicate=None):
        try:
            has_layer = MountedSpaceList(context.MountedSpaces).HasLayer().any()
            all_occupied = all(ms.IsOccupied() for ms in context.MountedSpaces)
            keg_exclusive = context.IsKegExclusivePallet()
            if has_layer and all_occupied and (not keg_exclusive):
                return True
        except Exception:
            pass

        context.add_execution_log("Palete nao se encaixa na regra de nao layer. Executando proxima regra.")
        return False

    def execute(self, context, item_predicate=None, mounted_space_predicate=None):
        # select items: NotMarketplace, NotChopp, NotIsotonicWater, WithAmountRemaining, ordered by amount remaining desc
        items = (
            ItemList(context.GetItems())
            .NotMarketplace()
            .Matching(item_predicate)
            .NotChopp()
            .NotIsotonicWater()
            .WithAmountRemaining()
            .OrderedByAmountRemainingDesc()
        )

        # filtered spaces: layer mounted spaces ordered by layer and occupation
        filtered_spaces = MountedSpaceList(context.MountedSpaces).HasLayer().OrderByLayerAndOccupation()
        containers = filtered_spaces.GetDisposableOrReturnableType()
        # collect containers from filtered spaces (flatten)
        # containers = []
        # for ms in filtered_spaces:
        #     containers.extend(getattr(ms, 'Containers', getattr(ms, 'containers', [])) or [])
        #     context.add_execution_log(f"Espaco montado {ms} com containers {getattr(ms, 'Containers', getattr(ms, 'containers', [])) or []}")

        # first phase: try to add remaining items to disposable/returnable containers on layer spaces
        for item in items:
            for container in containers:
                # find mounted_space that contains this container
                mounted_space = None
                for ms in filtered_spaces:
                    conts = getattr(ms, 'Containers', getattr(ms, 'containers', [])) or []
                    for c in conts:
                        # prefer Equals method if present
                        try:
                            if hasattr(c, 'Equals') and c.Equals(container):
                                mounted_space = ms
                                break
                        except Exception:
                            pass
                        if c == container:
                            mounted_space = ms
                            break
                    if mounted_space is not None:
                        break

                if mounted_space is None:
                    continue

                # can we add the whole remaining amount?
                if not context.domain_operations.can_add(context, mounted_space, item, item.AmountRemaining):
                    continue

                pallet_setting = item.Product.PalletSetting
                factor = item.Product.GetFactor(mounted_space.Space.Size)

                quantity = int(self.factor_converter.Quantity(item.AmountRemaining, factor, pallet_setting))

                occupation = int(self.factor_converter.Occupation(quantity, mounted_space.Space.Size, item, context.Settings.get('OccupationAdjustmentToPreventExcessHeight', False)))

                # Add product to the mounted space (space object expected)
                context.AddProduct(mounted_space.Space, item, quantity, 0, 0, occupation)
                context.add_execution_log(f"Item adicionado {item.Code} no espaco {mounted_space.Space.Number} / {mounted_space.Space.sideDesc} na quantidade {quantity}")

                if item.AmountRemaining == 0:
                    break

        # second phase: attempt to add remaining items on best spaces with same container types
        filtered_items_updated = (
            ItemList(context.GetItems())
            .NotChopp()
            .NotIsotonicWater()
            .WithAmountRemaining()
            .OrderedByAmountRemainingDesc()
        )

        for item in filtered_items_updated:
            # build predicate that matches mounted spaces with same container type(s)
            def same_type_pred(ms):
                for c in getattr(ms, 'Containers', getattr(ms, 'containers', [])) or []:
                    pb = getattr(c, 'ProductBase', None)
                    if pb is None:
                        continue
                    ct = getattr(pb, 'ContainerType', getattr(pb, 'container_type', None))
                    if ct in (ContainerType.ISOTONIC_WATER, ContainerType.RETURNABLE, ContainerType.DISPOSABLE):
                        return True
                return False

            pallets_with_same_type = MountedSpaceList(context.MountedSpaces).WithSameType(same_type_pred).OrderByLayerAndOccupation()

            if pallets_with_same_type and len(list(pallets_with_same_type)) > 0:
                # delegate to domain operations to add on best space
                context.domain_operations.add_on_best_space(context, pallets_with_same_type, item)
