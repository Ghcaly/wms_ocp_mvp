from ...domain.itemList import ItemList
from ...domain.space_list import SpaceList
from ...domain.base_rule import BaseRule
from ...domain.container_type import ContainerType


class PackageRule(BaseRule):
    def __init__(self, factor_converter = None):
        super().__init__()
        self.factor_converter = factor_converter

    def _get_returnable_spaces(self, context):
        """Return only spaces backed by a pure-Returnable mounted space (or empty spaces).

        Package/Market items are placed on top of Returnable pallets (glass bottles),
        not on CHOPP, Isotonic, Disposable, or mixed pallets.
        A bay is eligible only when every product already on it is Returnable type.
        """
        candidate_spaces = []
        for space in context.get_not_full_spaces():
            ms = context.get_mounted_space(space) if hasattr(context, 'get_mounted_space') else context.GetMountedSpace(space)
            if ms is None:
                candidate_spaces.append(space)
                continue

            containers = getattr(ms, 'Containers', getattr(ms, 'containers', []))
            if not containers:
                candidate_spaces.append(space)
                continue

            # Keep bays that already have Package-type products on them
            has_package_base = any(
                getattr(getattr(c, 'ProductBase', None), 'ContainerType', None) == ContainerType.PACKAGE
                for c in containers
            )
            if has_package_base:
                candidate_spaces.append(space)
                continue

            # Include only if every product in every container is Returnable
            all_ret = True
            found_product = False
            for container in containers:
                products = getattr(container, '_products', None)
                if products is None:
                    products = getattr(container, 'products', [])
                for mp in products:
                    prod = getattr(mp, 'Product', getattr(mp, 'product', None))
                    if prod is None:
                        continue
                    found_product = True
                    if getattr(prod, 'ContainerType', None) != ContainerType.RETURNABLE:
                        all_ret = False
                        break
                if not all_ret:
                    break

            if found_product and all_ret:
                candidate_spaces.append(space)

        return SpaceList(candidate_spaces)

    def should_execute(self, context, item_predicate=None, mounted_space_predicate=None):

        items = ItemList(context.get_items()).is_package().with_amount_remaining().ordered_by_amount_remaining_desc()
        if not items:
            context.add_execution_log("Não foram encontrados itens marketplace com quantidade a paletizar, parando execução da regra")
            return False

        available_spaces = self._get_returnable_spaces(context).ordered_by_package_then_occupation(context)
        if not available_spaces:
            context.add_execution_log("Não foram encontradas baias não cheias para paletizar os itens marketplace, parando execução da regra")
            return False

        return True

    def execute(self, context):

        items = ItemList(context.get_items()).is_package().with_amount_remaining().ordered_by_amount_remaining_desc()

        available_spaces = self._get_returnable_spaces(context).ordered_by_package_then_occupation(context)

        for item in items:
            units_per_box = item.product.units_per_box
            if units_per_box == 0:
                continue

            for space in available_spaces:
                if item.amount_remaining < units_per_box:
                    break

                mounted_space = context.get_mounted_space(space)

                min_occupation = self.factor_converter.occupation(units_per_box, space.size, item, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))
                packages_quantity = 1
                retries = 0

                # while CanPalletizePackage equivalent
                while (context.domain_operations.can_add(context, space, item, units_per_box)
                       and item.amount_remaining >= units_per_box
                       and min_occupation <= space.size
                       and (mounted_space is None or mounted_space.occupation_remaining >= min_occupation)):

                    first_layer = mounted_space.get_next_layer() if mounted_space is not None else 0
                    quantity_of_layer = item.product.get_quantity_of_layer_to_space(space.size, units_per_box)
                    mounted_space = context.AddProduct(space, item, units_per_box, first_layer, quantity_of_layer, min_occupation, packages_quantity)
                    retries += 1
                    context.add_execution_log(f"Paletizando o item: {item.Code} na quantidade: {units_per_box} na baia: {mounted_space.Space.Number} / {mounted_space.Space.sideDesc} e ocupação {min_occupation}")
