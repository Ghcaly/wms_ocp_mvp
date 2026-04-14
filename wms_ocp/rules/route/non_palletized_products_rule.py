from ...domain.itemList import ItemList
from ...rules.route.pallet_group_subgroup_rule import PalletGroupSubGroupRule
from ...domain.base_rule import BaseRule

from ...domain.mounted_space_list import MountedSpaceList
from ...domain.container_type import ContainerType
import math

class NonPalletizedProductsRule(BaseRule):
    """
    Python port of C# NonPalletizedProductsRule.
    Faithful translation focusing on clarity and directness.
    """

    def __init__(self, factor_converter=None, pallet_group_rule=None):
        super().__init__()
        self.factor_converter = factor_converter
        self.pallet_group_rule = PalletGroupSubGroupRule(factor_converter=factor_converter)

    def get_default_item_predicate(self, context):
        return lambda x: x.NotChopp() and x.NotMarketplace() and x.NotIsotonicWater() and x.HasAmountRemaining()

    def get_default_mounted_space_predicate(self, context):
        return lambda x: x.HasSpaceAndNotBlocked() and x.NotLayer() and x.NotKegExclusive() and x.NotChopp()

    def get_custom_item_predicate(self, returnable: bool):
        """Return a predicate for items depending on `returnable` flag.

        Mirrors the C# GetCustomItemPredicate: when `returnable` is True,
        predicate requires `IsReturnable()`; otherwise requires `not IsReturnable()`.
        """
        if returnable:
            return lambda x: x.IsReturnable() and x.NotChopp() and x.NotIsotonicWater() and x.HasAmountRemaining()

        return lambda x: (not x.IsReturnable()) and x.NotChopp() and x.NotIsotonicWater() and x.HasAmountRemaining()

    def get_custom_mounted_space_predicate(self, returnable: bool):
        """Return a predicate for mounted spaces depending on `returnable` flag.

        Mirrors the C# GetCustomMountedSpacePredicate: when `returnable` is True,
        predicate checks the first pallet is returnable; otherwise checks disposable.
        """
        if returnable:
            return lambda x: x.GetFirstPallet().IsTypeBaseReturnable() and x.HasSpaceAndNotBlocked() and x.NotLayer() and x.NotKegExclusive() and x.NotChopp()

        return lambda x: x.GetFirstPallet().IsTypeBaseDisposable() and x.HasSpaceAndNotBlocked() and x.NotLayer() and x.NotKegExclusive() and x.NotChopp()

    def should_execute(self, context, item_predicate=None, mounted_space_predicate=None):
        item_predicate = item_predicate or self.get_default_item_predicate(context)
        mounted_space_predicate = mounted_space_predicate or self.get_default_mounted_space_predicate(context)

        items = ItemList(context.GetItems()).NotMarketplace().Matching(item_predicate)
        mounted_spaces = MountedSpaceList(context.MountedSpaces).Matching(mounted_space_predicate)

        if items.Any() and (mounted_spaces.Any() or context.Spaces):
            return True
        
        context.add_execution_log("Nao foram encontrados produtos ou baias para processamento na regra, parando execucao da regra")
        return False

    def execute(self, context, item_predicate=None, mounted_space_predicate=None):
        item_predicate = item_predicate or self.get_default_item_predicate(context)
        mounted_space_predicate = mounted_space_predicate or self.get_default_mounted_space_predicate(context)

        items = ItemList(context.GetItems()).NotMarketplace().Matching(item_predicate).ToList()
        mounted_spaces = MountedSpaceList(context.MountedSpaces).Matching(mounted_space_predicate).ToList()

        # context.add_execution_log(f"Quantidade de baias do caminhao filtradas. Nao layer, nao exclusivo para barril, com espaço e nao bloqueado - {len(mounted_spaces)}")
        # context.add_execution_log(f"Quantidade de items filtrados. Nao chopp, nao agua e com quantidade de venda restante - {len(items)}")

        container_types = [ContainerType.RETURNABLE, ContainerType.ISOTONIC_WATER, ContainerType.DISPOSABLE]
        
        for item in ItemList(items).OrderedByAmountRemainingDesc().ToList():
            # context.add_execution_log(f"Tenta adicionar o produto {item.Product.Code} nos pallets com os tipos {ContainerType.RETURNABLE}, {ContainerType.ISOTONIC_WATER}, {ContainerType.DISPOSABLE}")
            self._build_products_with_same_type_on_pallet(context, mounted_spaces, item, container_types)

        if not ItemList(items).WithAmountRemaining().Any():
            return

        context.add_execution_log("Juntando espacos para evitar remonte")
        context.add_execution_log("Adicionando os items nos pallets com o mesmo tipo")

        # Group spaces by GroupCode (not chopp, not bulk)
        grouped_spaces = self._get_grouped_spaces(mounted_spaces)
        context.domain_operations.join_grouped_spaces(context, items, grouped_spaces)
        self._build_products_on_pallet_with_same_group_and_type(context, mounted_spaces, items)

        if not ItemList(items).WithAmountRemaining().Any():
            return

        context.add_execution_log("Adicionando os items em 2 pallets do tipo do produto")
        self._build_product_on_2_pallets_with_same_type_of_product(context, items, mounted_spaces)

        if not ItemList(items).WithAmountRemaining().Any():
            return

        context.add_execution_log("Juntando espacos para evitar remonte")
        context.add_execution_log("Adicionando os items nos pallets do tipo retornavel")

        # Group returnable spaces by GroupCode/SubGroupCode/PackingCode
        returnable_grouped_spaces = self._get_returnable_grouped_spaces(mounted_spaces)
        context.domain_operations.join_grouped_spaces(context, items, returnable_grouped_spaces)

        context.add_execution_log("Adicionando os items nos pallets com o mesmo tipo")
        self._build_products_on_pallet_with_same_group_and_type(context, mounted_spaces, items)

    def _get_grouped_spaces(self, mounted_spaces):
        """Group spaces by GroupCode (excluding chopp and bulk)"""
        from itertools import groupby
        
        # Filter: not chopp, not bulk
        valid = [ms for ms in mounted_spaces 
                 if not any(c.IsTypeBaseChopp() for c in ms.Containers) 
                 and not any(c.Bulk for c in ms.Containers)]
        
        # Group by first container's ProductBase.PackingGroup.GroupCode
        valid.sort(key=lambda ms: ms.Containers[0].ProductBase.PackingGroup.GroupCode)
        grouped = [list(g) for k, g in groupby(valid, key=lambda ms: ms.Containers[0].ProductBase.PackingGroup.GroupCode)]
        
        # Filter groups with more than 1 space, order by count desc
        return sorted([g for g in grouped if len(g) > 1], key=len, reverse=True)

    def _get_returnable_grouped_spaces(self, mounted_spaces):
        """Group returnable spaces by (GroupCode, SubGroupCode, PackingCode)"""
        from itertools import groupby
        
        # Filter: has returnable containers
        returnable = [ms for ms in mounted_spaces 
                      if any(c.IsTypeBaseReturnable() for c in ms.Containers)]
        
        # C#: GroupBy(p => p.Containers[0].Products.GroupBy(mp => new { GroupCode, SubGroupCode, PackingCode }))
        # This is complex - we group by the *set* of unique (GroupCode, SubGroupCode, PackingCode) in first container's products
        def group_key(ms):
            products = ms.Containers[0].Products
            # Get unique tuples of (GroupCode, SubGroupCode, PackingCode)
            unique_keys = frozenset((mp.Product.PackingGroup.GroupCode, 
                                     mp.Product.PackingGroup.SubGroupCode, 
                                     mp.Product.PackingGroup.PackingCode) 
                                    for mp in products)
            return unique_keys
        
        returnable.sort(key=lambda ms: sorted(group_key(ms)))
        grouped = [list(g) for k, g in groupby(returnable, key=group_key)]
        
        # Filter groups with > 1, order by count desc then occupation desc
        result = [g for g in grouped if len(g) > 1]
        return sorted(result, key=lambda g: (-len(g), -sum(ms.Occupation for ms in g)))

    def _build_product_on_2_pallets_with_same_type_of_product(self, context, items, mounted_spaces):
        """Add items on 2 pallets with same product type"""
        for item in sorted(items, key=lambda i: -i.AmountRemaining):
            # C#: mountedSpaces.WithSameType(item.Product.ContainerType).OrderByLayerAndOccupation()
            # context.add_execution_log(f"Tenta adicionar o produto {item.Product.Code} nos pallets com o tipo {item.Product.ContainerType}")
            ordered_spaces = MountedSpaceList(mounted_spaces).WithSameType(item.Product.ContainerType).OrderByLayerAndOccupation().ToList()
            
            if len(ordered_spaces) > 1:
                context.domain_operations.AddOnBestSpace(context, ordered_spaces, item)


    def _build_products_on_pallet_with_same_group_and_type(self, context, mounted_spaces, items):
        """Execute group/subgroup rule and add products with same group and type"""
        if not context.Spaces:
            return

        context.add_execution_log("Chamando a regra PalletDeMesmoGrupoESubgrupo para os items e mountedSpaces filtrados anteriormente")

        # Execute group/subgroup rule sequence using helper predicates
        self._execute_group_subgroup_rule(
            context,
            self.get_custom_item_predicate(True),
            self.get_custom_mounted_space_predicate(True),
            validate_minimum_occupation=True
        )

        if context.Spaces:
            self._execute_group_subgroup_rule(
                context,
                self.get_custom_item_predicate(False),
                self.get_custom_mounted_space_predicate(False),
                validate_minimum_occupation=True
            )

        self._execute_group_subgroup_rule(
            context,
            self.get_custom_item_predicate(True),
            self.get_custom_mounted_space_predicate(True),
            validate_minimum_occupation=False
        )

        if context.Spaces:
            self._execute_group_subgroup_rule(
                context,
                self.get_custom_item_predicate(False),
                self.get_custom_mounted_space_predicate(False),
                validate_minimum_occupation=False
            )

        if not ItemList(items).WithAmountRemaining().Any():
            return

        container_types = [ContainerType.RETURNABLE, ContainerType.ISOTONIC_WATER, ContainerType.DISPOSABLE]
        
        for item in ItemList(items).OrderedByAmountRemainingDesc().ToList():
            # context.add_execution_log(f"Tenta adicionar o produto {item.Product.Code} nos pallets com os tipos {ContainerType.RETURNABLE}, {ContainerType.ISOTONIC_WATER}, {ContainerType.DISPOSABLE}")
            # C#: mountedSpaces.WithProducts().FilterByGroupCode(item.Product)
            filtered_spaces = MountedSpaceList(mounted_spaces).WithProducts().FilterByGroupCode(item.Product).ToList()
            self._build_products_with_same_type_on_pallet(context, filtered_spaces, item, container_types)

        if not ItemList(items).WithAmountRemaining().Any():
            return

        context.add_execution_log("Adicionando os items nos pallets com o mesmo tipo de produto")
        
        for item in ItemList(items).OrderedByAmountRemainingDesc().ToList():
            container_type = ContainerType.RETURNABLE if item.IsReturnable() else ContainerType.DISPOSABLE
            self._build_products_with_same_type_of_product_on_pallet(context, mounted_spaces, item, container_type)

    def _execute_group_subgroup_rule(self, context, item_predicate, mounted_space_predicate, validate_minimum_occupation):
        """Execute PalletGroupSubGroupRule with given predicates"""
        if self.pallet_group_rule:
            self.pallet_group_rule.ValidatingMinimumOccupationPercentage(validate_minimum_occupation).execute(
                context, item_predicate, mounted_space_predicate
            )

    def _build_products_with_same_type_on_pallet(self, context, mounted_spaces, item, container_types):
        """Build products with same type on pallet"""
        # C#: mountedSpaces.Where(x => x.Containers.GetProducts().Any(d => d.Product.PackingGroup.GroupCode == item.Product.PackingGroup.GroupCode))
        #     .WithSameType(containerTypes)
        #     .OrderBy(x => Diference(x.Containers.FirstOrDefault(d => containerTypes.Contains(d.ProductBase.ContainerType)), item.Product))
        #     .ThenBy(x => x.Occupation)
        
        # Filter: has products with same GroupCode
        # filtered = [ms for ms in mounted_spaces 
        #             if any(mp.Product.PackingGroup.GroupCode == item.Product.PackingGroup.GroupCode 
        #                    for c in ms.Containers for mp in c.Products)]
        
        # # Filter: has same type
        # filtered = MountedSpaceList(filtered).WithSameTypes(*container_types).ToList()
        
        # # Order by difference then occupation
        # ordered = sorted(filtered, key=lambda ms: (
        #     self._difference(self._get_first_container_with_type(ms.Containers, container_types), item.Product),
        #     ms.Occupation
        # ))

        filtered = MountedSpaceList(mounted_spaces).FilterByGroupCodeAny(item.Product)\
            .WithSameTypes(*container_types).OrderByDifferenceAndOccupation(item.Product)\
            .ToList()
        
        self._build_products_on_pallet(context, filtered, item)

    def _build_products_with_same_type_of_product_on_pallet(self, context, mounted_spaces, item, container_type):
        """Build products with same type of product on pallet"""
        # C#: mountedSpaces.WithSameType(containerType)
        #     .OrderBy(x => x.HasLayer())
        #     .ThenBy(x => Diference(x.Containers.FirstOrDefault(d => containerType.Contains(d.ProductBase.ContainerType)), item.Product))
        #     .ThenBy(x => x.Occupation)
        
        filtered = MountedSpaceList(mounted_spaces).WithSameType(container_type).ToList()
        
        ordered = sorted(filtered, key=lambda ms: (
            ms.HasLayer(),
            self._difference(self._get_first_container_with_type(ms.Containers, [container_type]), item.Product),
            ms.Occupation
        ))
        
        self._build_products_on_pallet(context, ordered, item)

    def _build_products_on_pallet(self, context, ordered_mounted_spaces, item):
        """Add item to ordered mounted spaces or empty spaces"""
        # context.add_execution_log(f"Ordenando as baias que contenham o mesmo tipo, onde o produto base seja {item.Product.Code}, por layer, ocupação e diferença entre os codigos de embalagem")
        # context.add_execution_log(f"Quantidade de baias ordenadas {len(ordered_mounted_spaces)}")

        if not ordered_mounted_spaces:
            return

        # Try to add on existing mounted spaces with products
        for ms in MountedSpaceList(ordered_mounted_spaces).WithProducts().ToList():
            self._update_context(context, item, ms.Space)
            if not item.HasAmountRemaining():
                break

        if not item.HasAmountRemaining():
            return

        # Try to add on empty spaces
        for space in context.Spaces:
            self._update_context(context, item, space)
            if not item.HasAmountRemaining():
                break

    def _update_context(self, context, item, space):
        """Add product to space if possible"""
        mounted_space = context.GetMountedSpace(space)
        pallet_setting = item.Product.PalletSetting
        factor = item.Product.GetFactor(space.Size)

        current_occupation = mounted_space.Occupation if mounted_space else 0
        free_occupation = int(space.Size) - current_occupation

        boxes = int(math.floor(self.factor_converter.QuantityPerFactor(free_occupation, item.AmountRemaining, factor, item, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))))
        ballast = int(math.floor(boxes / pallet_setting.QuantityBallast))
        occupation = self.factor_converter.Occupation(boxes, factor, pallet_setting, item, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))

        if not context.domain_operations.CanAdd(context, space, item, item.AmountRemaining):
            return

        mounted_space = context.AddProduct(space, item, boxes, 0, ballast, occupation)

        context.add_execution_log(f"Item adicionado {item.Code} no espaco {mounted_space.Space.Number} / {mounted_space.Space.sideDesc} - Quantidade: {boxes}")

    def _difference(self, container, product):
        """Calculate difference between container and product GroupAndSubGroup"""
        if not container:
            return float('inf')
        return abs(container.GroupAndSubGroup - product.GroupAndSubGroup)

    def _get_first_container_with_type(self, containers, container_types):
        """Get first container matching one of the container types"""
        for c in containers:
            if c.ProductBase.ContainerType in container_types:
                return c
        return None

