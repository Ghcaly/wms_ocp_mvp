
from decimal import Decimal
from typing import Iterable, List

from ...domain.mounted_space_list import MountedSpaceList
from ...domain.subsequences import SubsequenceGenerator
from ...domain.base_rule import BaseRule
from ...domain.itemList import ItemList
from itertools import combinations

from ...domain.space_size_extensions import space_size_chains


class PalletGroupSubGroupRule(BaseRule):
    """Faithful port of C# PalletGroupSubGroupRule, using SpaceSizeChain nodes."""

    def __init__(self, factor_converter=None):
        super().__init__()
        self._factor_converter = factor_converter
        self._minimumOccupationPercentage = 0
        self._validateMinimumOccupationPercentage = True

    def ValidatingMinimumOccupationPercentage(self, validateMinimumOccupation: bool):
        self._validateMinimumOccupationPercentage = validateMinimumOccupation
        return self

    def GetDefaultItemPredicate(self, context):
        return lambda i: (
            i.NotChopp()
            and i.NotMarketplace()
            and i.NotIsotonicWater()
            and i.HasAmountRemaining()
            and i.WithConfiguration(context.get_setting('IncludeTopOfPallet'))
        )

    def execute(self, context, item_predicate=None, mounted_space_predicate=None):
        if self._validateMinimumOccupationPercentage:
            self._minimumOccupationPercentage = context.get_setting('MinimumOccupationPercentage')

        filtered_items = ItemList(context.GetItems()).NotMarketplace().Matching(
            item_predicate or self.GetDefaultItemPredicate(context)
        ).OrderedByAmountRemainingDesc()

        unique_spaces = (
            MountedSpaceList(context.MountedSpaces)
            .NotBlocked()
            .Matching(mounted_space_predicate)
            .GetSpaces()
            .Concat(context.Spaces)
            .Distinct()
            .OrderedBySizeAndNumber()
        )

        for type_selector in [lambda it: it.isReturnable(), lambda it: it.isDisposable()]:
            self.calculate_by_type(filtered_items, context, type_selector, unique_spaces)

    # --- internal helpers ---
    def calculate_by_type(self, filtered_items: ItemList, context, type_selector, spaces: Iterable):
        items = filtered_items.Matching(lambda it: type_selector(it))

        for item in items.WithAmountRemaining():
            items_same = self.get_items_by_group_and_sub_group(items, item)
            if not items_same.Any():
                continue

            for size_node in list(space_size_chains()):
                # Pre-calculate factor dicts for all items (mirrors C# Select before CalculateBySize)
                items_with_factors = [
                    self.calculate_factor_by_space(it, size_node.Current, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))
                    for it in items_same
                ]
                self.calculate_by_size(context, item, items_with_factors, size_node, spaces)

    def calculate_factor_by_space(self, item, size_current, calculate_additional_occupation):
        factor = item.Product.GetFactor(size_current)
        boxes = self._factor_converter.occupation(item.AmountRemaining, factor, item.Product.PalletSetting, item, calculate_additional_occupation)
        return {'item': item, 'size': size_current, 'boxes_quantity': boxes, 'factor': factor}

    def subsequences(self, lst):
        result = []
        for r in range(1, len(lst) + 1):
            for combo in combinations(lst, r):
                result.append(list(combo))
        return result

    def calculate_by_size(self, context, item, items_same_group_and_subgroup, size_node, spaces):
        # items_same_group_and_subgroup is already a list of factor dicts (pre-calculated)
        size_value = size_node.Current
        spaces_with_current_size = [s for s in spaces if int(getattr(s, 'Size', getattr(s, 'size', 0)) or 0) == int(size_value)]
        for space in spaces_with_current_size:
            mounted_space = context.GetMountedSpace(space)

            if self.is_mounted_space_occupied(mounted_space, context):
                continue

            if not item.HasAmountRemaining():
                break

            current_occupation = mounted_space.Occupation if mounted_space is not None else 0
            free_occupation = int(size_value) - int(current_occupation)

            # Generate subsequences of pre-calculated factor dicts (mirrors C# Subsequences())
            sequences = list(SubsequenceGenerator(limit=30000).subsequences(items_same_group_and_subgroup))

            quantity_to_remaining = (
                self.get_quantity_to_remaining_space(mounted_space, space, item, context)
                if mounted_space is not None
                else 0
            )

            filtered_sequences = [
                seq for seq in sequences
                if (
                    mounted_space is None
                    or (quantity_to_remaining > 0 and sum(x["boxes_quantity"] for x in seq) <= free_occupation)
                )
            ]

            sequences = self.calculate_minimum_occupation_percentage(size_value, filtered_sequences, context)
            if not any(sequences):
                continue

            selected_sequences = (
                min(sequences, key=lambda seq: free_occupation - sum(x['boxes_quantity'] for x in seq))
                if sequences else None
            )

            if selected_sequences is None:
                continue

            if self.has_next_space(context.Spaces, size_node) and self.next_occupation_percentage_is_bigger_than_current(size_node, selected_sequences):
                continue

            ordered_sequences = sorted(
                selected_sequences,
                key=lambda x: getattr(x["item"], "amount_remaining", 0),
                reverse=True
            )

            self.add_product(context, space, item, size_value, ordered_sequences)

    def has_next_space(self, spaces, size_chain):
        return (
            getattr(size_chain, 'Next', None) is not None
            and any(getattr(s, 'Size', getattr(s, 'size', None)) == size_chain.Next for s in spaces)
        )


    def next_occupation_percentage_is_bigger_than_current(self, size_chain, ordered_sequences):
        current_occupation_percentage = (
            sum(x['boxes_quantity'] for x in ordered_sequences) * 100
        ) / size_chain.Current

        next_occupation_percentage = (
            sum(x['boxes_quantity'] for x in ordered_sequences) * 100
        ) / size_chain.Next

        # return False
        return next_occupation_percentage >= current_occupation_percentage

    def must_skip_default_mounted_space(self, context, is_mounted_default):
        return is_mounted_default and not context.get_setting('NotMountBulkPallets')

    def calculate_minimum_occupation_percentage(self, size, sequences, context):
        if self._minimumOccupationPercentage > 0:
            minimum_quantity = int(size * self._minimumOccupationPercentage / 100)
            return [s for s in sequences if sum(x['boxes_quantity'] for x in s) >= minimum_quantity]
        return sequences

    def get_quantity_to_add(self, sequence, factor):
        item = sequence["item"]
        if factor.Quantity > item.AmountRemaining:
            return item.AmountRemaining
        return factor.Quantity

    def add_product(self, context, space, item, size, ordered_sequence):
        for seq in ordered_sequence:
            seq_item = seq['item']
            factor = seq_item.Product.GetFactor(size)
            to_add = self.get_quantity_to_add(seq, factor)
            is_mounted_default = False
            existing_mounted_space = context.GetMountedSpace(space)
            if existing_mounted_space is None:
                is_mounted_default = True

            if not context.domain_operations.CanAdd(context, space, seq_item, to_add):
                if (self.must_skip_default_mounted_space(context, is_mounted_default)):
                    continue

                to_add = int(self.get_quantity_to_remaining_space(existing_mounted_space, space, item, context))

                if not context.domain_operations.CanAdd(context, space, seq_item, to_add):
                    continue

            occupation = self.calculate_occupation(space, item, seq['boxes_quantity'], to_add, is_mounted_default, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))
            mounted_space = self.AddProduct(context, space, seq_item, to_add, occupation)
            if mounted_space is not None:
                mounted_space.GetFirstPallet().SetProductBase(item.Product)

    def AddProduct(self, context, space, item, quantity, occupation):
        first_layer = 0
        quantity_of_layer = int(quantity / item.Product.PalletSetting.QuantityBallast) or 0
        mounted_space = context.AddProduct(space, item, int(quantity), first_layer, quantity_of_layer, occupation)

        context.add_execution_log(f"Pallet adicionado na baia {mounted_space.Space.Number} / {mounted_space.Space.sideDesc}, tamanho {int(mounted_space.Space.Size)} CC com {quantity} itens de {item.Product.Code}-{item.Product.Name}, ocupacao {occupation} CC")
        return mounted_space

    # snake_case alias for portability
    def add_product_exact(self, *args, **kwargs):
        return self.AddProduct(*args, **kwargs)

    def get_quantity_to_remaining_space(self, mounted_space, space, item, context):
        if mounted_space is None:
            factor = item.Product.get_factor(space.Size)

            if (factor.Quantity is not None and item.AmountRemaining >= factor.Quantity):
                return factor.Quantity
            return int(self._factor_converter.QuantityToRemainingSpace(space, Decimal(space.Size), item, context.Settings))
        return int(self._factor_converter.QuantityToRemainingSpace(mounted_space, item, context.Settings))

    def calculate_occupation(self, space, item, occupation, to_add, is_mounted_space_default, calculate_additional_occupation):
        if not is_mounted_space_default:
            return occupation
        return round(self._factor_converter.occupation(to_add, space.Size, item, calculate_additional_occupation), 2)

    def is_mounted_space_occupied(self, mounted_space, context):
        if mounted_space is None:
            return False
        if getattr(context, 'Kind', None) == 'Mixed':
            return mounted_space.OccupationRemaining <= 0
        return mounted_space.Occupation > 0

    def get_items_by_group_and_sub_group(self, items: ItemList, item):
        return items.Matching(lambda x: x.Product.PackingGroup.GroupCode == item.Product.PackingGroup.GroupCode and x.Product.PackingGroup.SubGroupCode == item.Product.PackingGroup.SubGroupCode)
