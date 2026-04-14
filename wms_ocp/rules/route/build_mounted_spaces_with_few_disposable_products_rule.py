from ...domain.base_rule import BaseRule
from decimal import Decimal


class BuildMountedSpacesWithFewDisposableProductsRule(BaseRule):
    """Faithful, straightforward port of the C# BuildMountedSpacesWithFewDisposableProductsRule.

    This implementation calls attributes and methods directly (no defensive attribute checks)
    to stay close to the C# original, as requested.
    """

    def __init__(self, factor_converter = None):
        super().__init__()
        self._factor_converter = factor_converter

    def should_execute(self, context, item_predicate=None, mounted_space_predicate=None) -> bool:
        # mirror C# ShouldExecute: check JoinDisposableContainers setting
        if context.get_setting('JoinDisposableContainers'):
            return True
        context.add_execution_log(f"Motivo - Configuração 'JoinDisposableContainers' está desabilitada")
        return False

    def execute(self, context):
        # Obtain all disposable mounted spaces ordered by occupation (ascending)
        disposables = [m for m in context.mounted_spaces if m.is_disposable]
        disposables_sorted = sorted(disposables, key=lambda m: m.occupation)

        for space1 in disposables_sorted:
            if space1.occupation >= context.get_setting('MinimumQuantityToJoinDisposables', 1):
                continue

            disposables2 = sorted(disposables, key=lambda m: m.occupation)
            for space2 in [s for s in disposables2 if s is not space1]:
                # quantity of distinct products on first and second mounted spaces
                quantityDifferentItemsOnSpace1 = len({mp.product.code_promax for mp in space1.get_first_pallet().get_products()})
                quantityDifferentItemsOnSpace2 = len({mp.product.code_promax for mp in space2.get_first_pallet().get_products()})

                # choose bigger and smaller (add to bigger)
                if space1.space.size > space2.space.size:
                    mountedSpaceToAdd = space1
                    mountedSpaceToRemove = space2
                else:
                    mountedSpaceToAdd = space2
                    mountedSpaceToRemove = space1

                # decide if we can build the disposable mounted space
                if not self._should_build_disposable_mounted_space(mountedSpaceToAdd, mountedSpaceToRemove, quantityDifferentItemsOnSpace1, quantityDifferentItemsOnSpace2, context.get_setting('OccupationAdjustmentToPreventExcessHeight', False), context):
                    continue

                # select returnable mounted spaces (not keg-exclusive / returnable and above occupation threshold)
                # Here we use available helpers on the context.mounted_spaces when present; keep semantics close to C#
                returnable_spaces = [m for m in context.mounted_spaces if m.is_returnable(context) and not m.is_keg_exclusive() and m.occupation > context.get_setting('MinimumOccupationToSwitchDisposableMountedSpaces', 0)]

                # add returnable products into containers
                self._add_returnable_products_on_container(context, mountedSpaceToAdd, mountedSpaceToRemove, returnable_spaces)

    def _add_returnable_products_on_container(self, context, mountedSpaceToAdd, mountedSpaceToRemove, returnableMountedSpaces):
        for returnableMountedSpace in returnableMountedSpaces:
            # group mounted products by packing group code
            mounted_products = returnableMountedSpace.get_products()
            mountedProductsByPackingGroup = {}
            for mp in mounted_products:
                code = mp.product.packing_group_id
                mountedProductsByPackingGroup.setdefault(code, []).append(mp)

            quantityDifferentPackingGroups = len([g for g in mountedProductsByPackingGroup.values()])
            if quantityDifferentPackingGroups <= 1:
                continue

            changedProducts = context.domain_operations.change_product_full_space(context, mountedSpaceToAdd, mountedSpaceToRemove)
            if not changedProducts:
                continue

            # order groups by total quantity per factor (descending) and skip the first
            groups = list(mountedProductsByPackingGroup.values())
            def group_value(g):
                return sum(self._factor_converter.quantity_per_factor(returnableMountedSpace.space.size, mp.amount, mp.product.get_factor(returnableMountedSpace.space.size), mp.item, context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)) for mp in g)

            groups_sorted = sorted(groups, key=lambda g: group_value(g), reverse=True)
            mountedProductsWithLessPackingGroupsQuantity = groups_sorted[1:]

            # add returnable products with less packing groups quantity into the freed mounted space
            self._add_returnable_products_with_less_packing_group_quantity_on_container(context, mountedSpaceToRemove, returnableMountedSpace, mountedProductsWithLessPackingGroupsQuantity)
            break

    def _add_returnable_products_with_less_packing_group_quantity_on_container(self, context, mountedSpaceToRemove, returnableMountedSpace, groups):
        for group in groups:
            for mountedProduct in group:
                item = mountedProduct.item
                if not context.domain_operations.can_add(context, mountedSpaceToRemove, item, mountedProduct.amount):
                    continue

                occupation = self._factor_converter.occupation(mountedProduct.amount, returnableMountedSpace.space.size, mountedProduct.item.product.PalletSetting, mountedProduct.item, context.get_setting('OccupationAdjustmentToPreventExcessHeight', False))
                boxes = self._factor_converter.quantity_per_factor(returnableMountedSpace.space.size, mountedProduct.amount, mountedProduct.product.get_factor(returnableMountedSpace.space.size), mountedProduct.item, context.get_setting('OccupationAdjustmentToPreventExcessHeight', False))

                # add product into the freed mounted space
                context.add_product(mountedSpaceToRemove.space, item, int(boxes), occupation)

    def _should_build_disposable_mounted_space(self, spaceToAdd, spaceToRemove, quantityDifferentItensOnSpace1, quantityDifferentItensOnSpace2, calculateAdditionalOccupation, context) -> bool:
        # boxes on spaceToRemove according to factor converter
        boxesOnSpaceToRemove = 0
        for p in spaceToRemove.get_first_pallet().get_products():
            boxesOnSpaceToRemove += self._factor_converter.quantity_per_factor(spaceToRemove.space.size, p.amount, p.product.get_factor(spaceToAdd.space.size), p.item, calculateAdditionalOccupation)

        occupation_remaining = spaceToAdd.space.size - spaceToAdd.occupation
        boxesOnSpaceToRemoveFitsOnSpaceToAdd = boxesOnSpaceToRemove < occupation_remaining

        sumOfDifferentItems = quantityDifferentItensOnSpace1 + quantityDifferentItensOnSpace2
        max_diff = context.get_setting('MaximumQuantityDifferentProductsOnPallet', 10)

        sumOfDifferentItemsIsSmallerThanSpaceToAddSize = sumOfDifferentItems < int(spaceToAdd.space.size)
        sumOfDifferentItemsIsSmallerThanMaximum = sumOfDifferentItems < max_diff

        return boxesOnSpaceToRemoveFitsOnSpaceToAdd and sumOfDifferentItemsIsSmallerThanMaximum and sumOfDifferentItemsIsSmallerThanSpaceToAddSize
