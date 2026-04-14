from typing import List, Optional

from ...domain.mounted_space_list import MountedSpaceList
from ...domain.space_list import SpaceList
from ...domain.subsequences import SubsequenceGenerator

from ..route.non_layer_on_layer_pallet_rule import NonLayerOnLayerPalletRule
from ...domain.itemList import ItemList
from ...domain.base_rule import BaseRule
from ...domain.container_type import ContainerType


class IsotonicWaterRule(BaseRule):
	"""Faithful, direct-port of C# IsotonicWaterRule.

	This implementation calls domain/context methods directly (no defensive
	hasattr/try guards) as requested. It uses the Python helpers already
	implemented (MountedSpaceList, ItemList, domain operations) and follows
	the same control flow as the C# rule.
	"""

	def __init__(self, factor_converter=None):
		super().__init__()
		self.factor_converter = factor_converter
		self.non_layer_on_layer_pallet_rule = NonLayerOnLayerPalletRule()
		self._validate_minimum_occupation = True

	def _get_items(self, context):
		return ItemList(context.GetItems()).IsIsotonicWater().WithAmountRemaining()

	def should_execute(self, context, item_predicate=None, mounted_space_predicate=None):
		if self._get_items(context).Any():
			return True
		# context.AddExecutionLog("Motivo - Nenhum item isotonico encontrado, regra não será executada")
		return False

	def execute(self, context, item_predicate=None, mounted_space_predicate=None):
		min_occupation = context.get_setting('MinimumOccupationPercentage') if self._validate_minimum_occupation else 0
		context.add_execution_log(f"IsotonicWaterRule: iniciando execução com MinimumOccupationPercentage={min_occupation}")

		# 1) Add water on the first empty space
		space = None
		context.add_execution_log("IsotonicWaterRule: tentando adicionar água no primeiro espaço vazio")
		first_space = self._add_water_on_first_empty_space(context, min_occupation)
		if first_space is not None:
			space = first_space
			context.add_execution_log(f"IsotonicWaterRule: espaço {first_space.Number}/{first_space.sideDesc} usado")

		# 2) Grouped spaces to avoid remount
		mounted_spaces = MountedSpaceList(context.MountedSpaces).HasSpaceAndNotBlocked().ToList()
		filtered = [p for p in mounted_spaces if (not any(c.IsTypeBaseChopp() for c in p.Containers)) and (not any(c.Bulk for c in p.Containers)) and p.NotLayer()]

		# group by first container ProductBase.PackingGroup.GroupCode and keep groups with more than one space
		groups = {}
		for p in filtered:
			key = p.Containers[0].ProductBase.PackingGroup.GroupCode
			groups.setdefault(key, []).append(p)
		grouped_spaces = [v for v in groups.values() if len(v) > 1]
		grouped_spaces.sort(key=lambda x: len(x), reverse=True)

		items_to_join = self._get_items(context)
		context.add_execution_log(f"IsotonicWaterRule: tentando juntar {len(grouped_spaces)} grupos de espaços")
		context.domain_operations.join_grouped_spaces(context, items_to_join, grouped_spaces)

		context.add_execution_log("IsotonicWaterRule: tentando adicionar água no primeiro espaço vazio (segunda tentativa)")
		second_space = self._add_water_on_first_empty_space(context, min_occupation)
		if second_space is not None:
			space = second_space

		for item in self._get_items(context).OrderedByAmountRemainingDesc():
			self._add_product(context, space, item)

			candidate = MountedSpaceList(context.MountedSpaces).HasSpaceAndNotBlocked().WithSameType(ContainerType.DISPOSABLE).OrderByLayerOccupationAndDifference(item.Product)\
			 .FirstOrDefault()

			space = candidate.Space if candidate is not None else None
			if space is not None:
				self._add_product(context, space, item)

			self._add_product_on_base_type_space(context, item, ContainerType.DISPOSABLE)
			self._add_product_on_base_type_space(context, item, ContainerType.RETURNABLE, filter_remount=True)

			# delegated rule
			context.add_execution_log("IsotonicWaterRule: executando NonLayerOnLayerPalletRule")
			self.non_layer_on_layer_pallet_rule.execute(context, lambda x: x.IsIsotonicWater() and x.HasAmountRemaining())

			# best_spaces = MountedSpaceList(context.MountedSpaces).HasSpaceAndNotBlocked().IsDisposable().OrderByLayerAndOccupation()
			best_spaces = MountedSpaceList(context.MountedSpaces).HasSpaceAndNotBlocked().WithSameType(ContainerType.DISPOSABLE).OrderByLayerAndOccupation()
			if best_spaces.Count() > 1:
				context.domain_operations.AddOnBestSpace(context, best_spaces, item)

			self._add_product_on_base_type_space(context, item, ContainerType.RETURNABLE)

			# best_space_with_group = MountedSpaceList(context.MountedSpaces).HasSpaceAndNotBlocked().IsReturnable().OrderByLayerAndDifference(item.Product).FirstOrDefault()
			best_space_with_group = MountedSpaceList(context.MountedSpaces).HasSpaceAndNotBlocked().WithSameType(ContainerType.RETURNABLE).OrderByLayerAndDifference(item.Product).FirstOrDefault()
			self._add_product_on_base_type_space_with_less_occupation(context, item, best_space_with_group, ContainerType.DISPOSABLE)

			# best_space_occupation = MountedSpaceList(context.MountedSpaces).HasSpaceAndNotBlocked().IsDisposable().OrderByLayerRemountDescAndOccupation().FirstOrDefault()
			best_space_occupation = MountedSpaceList(context.MountedSpaces).HasSpaceAndNotBlocked().WithSameType(ContainerType.DISPOSABLE).OrderByLayerRemountDescAndOccupation().FirstOrDefault()
			self._add_product_on_base_type_space_with_less_occupation(context, item, best_space_occupation, ContainerType.DISPOSABLE)

			self._split_product_on_two_returnable_spaces_with_less_occupation(context, item)

			# chopp_spaces = MountedSpaceList(context.MountedSpaces).HasSpaceAndNotBlocked().IsChopp().NotKegExclusive().OrderByNotRemountDescAndOccupation()
			chopp_spaces = MountedSpaceList(context.MountedSpaces).HasSpaceAndNotBlocked().WithSameType(ContainerType.CHOPP).NotKegExclusive().OrderByNotRemountDescAndOccupation()
			for chopp in chopp_spaces:
				self._add_product(context, chopp.Space, item)

			container_type = ContainerType.RETURNABLE if item.IsReturnable() else ContainerType.DISPOSABLE
			predicate = lambda ms, ct=container_type: any(c.ProductBase.ContainerType == ct for c in ms.Containers)
			best_space = MountedSpaceList(context.MountedSpaces).HasSpaceAndNotBlocked().matching(predicate).OrderByLayerRemountDescAndOccupation().FirstOrDefault()
			self._add_product_on_base_type_space_with_less_occupation(context, item, best_space, ContainerType.DISPOSABLE)

	# ---- helpers (direct calls, no defensive guards) ----
	def _add_water_on_first_empty_space(self, context, min_occupation: int):
		empty_space = SpaceList(context.Spaces).FirstOrDefault()
		if empty_space is not None:
			self._add_water_on_empty_space(context, empty_space, min_occupation)
			return empty_space
		return None

	def _add_water_on_empty_space(self, context, space, minimum_occupation: int):
		items = self._get_items(context)
		items_with_occupation = [
			{
				'item': x,
				'occupation': self.factor_converter.Occupation(x.AmountRemaining, x.Product.GetFactor(space.Size), x.Product.PalletSetting, x, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))
			}
			for x in items
		]

		total_occ = sum(p['occupation'] for p in items_with_occupation)
		if total_occ <= int(space.Size):
			for it in items.OrderedByAmountRemainingDesc():
				self._add_product(context, space, it)
			return

		# generate all subsequences (C# Subsequences())
		def generate_subsequences(items_list):
			"""Generate all non-empty subsequences of items."""
			from itertools import combinations
			for r in range(1, len(items_list) + 1):
				for combo in combinations(items_list, r):
					yield list(combo)

		# sequences = [seq for seq in generate_subsequences(items_with_occupation) if sum(x['occupation'] for x in seq) <= int(space.Size)] #temporario

		sequences = list(SubsequenceGenerator(limit=30000).subsequences(items_with_occupation))

		sequences = [seq for seq in sequences if sum(x['occupation'] for x in seq) <= int(space.Size)]

		if minimum_occupation > 0:
			sequences = [seq for seq in sequences if sum(x['occupation'] for x in seq) >= int(space.Size) * minimum_occupation / 100]

		if not sequences:
			return

		# filter by MaxPackageGroups if setting enabled
		max_groups = context.get_setting('MaxPackageGroups', 0)
		should_limit = context.get_setting('ShouldLimitPackageGroups', False)
		if should_limit:
			sequences = [seq for seq in sequences if len(set(x['item'].Product.PackingGroup.GroupCode for x in seq)) <= max_groups]

		if not sequences:
			return

		sequence_item = max(sequences, key=lambda seq: sum(x['occupation'] for x in seq))
		for entry in sorted(sequence_item, key=lambda x: -x['item'].AmountRemaining):
			self._add_product(context, space, entry['item'])

	def _add_product(self, context, space, item):
		if not item.HasAmountRemaining() or space is None:
			return
		if not context.domain_operations.CanAdd(context, space, item, item.AmountRemaining):
			return
		factor = item.Product.GetFactor(space.Size)
		occupation = self.factor_converter.Occupation(item.AmountRemaining, factor, item.Product.PalletSetting, item, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))
		mounted_space = context.AddProduct(space, item, item.AmountRemaining, occupation)
		context.add_execution_log(f"Adicionado {item.Code} quantidade {item.AmountRemaining} no espaco {space.Number} / {space.sideDesc}, ocupacao de {mounted_space.Occupation}")

	def _add_product_on_base_type_space(self, context, item, container_type, filter_remount=False):
		if not item.HasAmountRemaining():
			return
		filtered_spaces = MountedSpaceList(context.MountedSpaces).HasSpaceAndNotBlocked().WithSameType(container_type)
		if filter_remount:
			filtered_spaces = filtered_spaces.IsRemount()
		filtered_spaces = filtered_spaces.OrderByLayerAndOccupation()
		if filtered_spaces.Any():
			space = filtered_spaces.FirstOrDefault().Space
			self._add_product(context, space, item)

	def _add_product_on_base_type_space_with_less_occupation(self, context, item, space, container_type):
		if space is None or not item.HasAmountRemaining():
			return
		best_spaces = MountedSpaceList(context.MountedSpaces).HasSpaceAndNotBlocked().WithSameType(container_type).OrderByLayerRemountDescAndOccupation()
		if not best_spaces.Any():
			return
		for diff in best_spaces:
			context.domain_operations.AddOn2Spaces(context, space.Space, diff.Space, item)
			if not item.HasAmountRemaining():
				break

	def _split_product_on_two_returnable_spaces_with_less_occupation(self, context, item):
		best_spaces = MountedSpaceList(context.MountedSpaces).HasSpaceAndNotBlocked().WithSameType(ContainerType.RETURNABLE).OrderByLayerRemountDescAndOccupation()
		if best_spaces.Count() < 2:
			return
		space1 = None
		space2 = None
		for best_space in best_spaces:
			if space1 is None:
				space1 = best_space
			else:
				space2 = best_space
			if space1 is None or space2 is None:
				continue
			context.domain_operations.AddOn2Spaces(context, space1.Space, space2.Space, item)
			if all((not getattr(c, 'Remount', False)) and getattr(c, 'is_pallet', False) for c in space2.Containers):
				space2 = None
			else:
				space1 = None
			if not item.HasAmountRemaining():
				break

	def WithoutMinOccupationValidation(self):
		self._validate_minimum_occupation = False
		return self

