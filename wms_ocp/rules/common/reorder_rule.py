from ...domain.base_rule import BaseRule
from ...domain.context import RouteRuleContext
from ...domain.mounted_product_list import MountedProductList


class ReorderRule(BaseRule):
    """Faithful Python port of C# ReorderRule.
    
    Reorders products within containers to optimize assembly sequence and pallet organization.
    
    Flow:
    1. Reset all assembly sequences to 0
    2. Cache settings flags (OrderPalletByPackageCodeOccupation, OrderPalletByCancha)
    3. Execute two-pass reordering: layer products first, then non-layer
    4. For each container, order products by type priority:
       - Layer products (if validate_layer=True)
       - Base pallet products
       - Chopp (draft beer barrels)
       - Returnable products
       - Disposable products
       - Isotonic water
       - Top of pallet products
       - Marketplace products (Package, BoxTemplate)
    """
    def __init__(self):
        super().__init__()
        self._order_pallet_by_package_code_occupation = False
        self._order_pallet_by_cancha = False

    def should_execute(self, context, item_predicate=None, mounted_space_predicate=None):
        """C#: ShouldExecute - check if rule should execute based on settings"""
        order_by_package = context.Settings.get('OrderPalletByPackageCodeOccupation', False)
        order_by_cancha = context.Settings.get('OrderPalletByCancha', False)
        isotonic_custom = context.Settings.get('IsotonicTopPalletCustomOrderRule', False)

        if order_by_package and order_by_cancha and isotonic_custom:
            context.add_execution_log("Configurações conflitantes detectadas, a regra não será executada")
            return False

        return True

    def execute(self, context, item_predicate=None, mounted_space_predicate=None):
        """C#: Execute - main execution flow"""
        # Reset all assembly sequences to 0
        for mounted_space in context.MountedSpaces:
            for container in mounted_space.GetContainers():
                for product in container.GetProducts():
                    product.SetAssemblySequence(0)

        # Cache settings flags
        self._order_pallet_by_package_code_occupation = context.Settings.get('OrderPalletByPackageCodeOccupation', False)
        self._order_pallet_by_cancha = context.Settings.get('OrderPalletByCancha', False)

        # Two-pass reordering: layer products first, then non-layer
        self._reorder_pallets(context, validate_layer=True)
        self._reorder_pallets(context, validate_layer=False)

    def _reorder_pallets(self, context, validate_layer=False):
        """C#: ReordenarPallets - reorder pallets with layer validation"""
        include_top_of_pallet = context.Settings.get('IncludeTopOfPallet', False)
        order_pallet_by_product_group = context.Settings.get('OrderPalletByProductGroup', False)

        for mounted_space in context.MountedSpaces:
            # if mounted_space.Space.number==3 and mounted_space.Space.side=='77':#temporatio
            #     print("aqui")
            for container in mounted_space.Containers:
                # Get products ordered by delivery order
                products = MountedProductList(container.Products).OrderByOrderNumber()

                # Filter by layer
                if validate_layer:
                    products = products.OnlyLayer()
                else:
                    products = products.NotLayer()

                if not products.Any():
                    continue

                # Order pallet by cancha or standard order
                if self._order_pallet_by_cancha:
                    self._order_pallet_by_cancha_method(
                        validate_layer, include_top_of_pallet, 
                        order_pallet_by_product_group, container, products
                    )
                else:
                    self._order_pallet(
                        validate_layer, include_top_of_pallet,
                        order_pallet_by_product_group, container, products
                    )

    # --- ordering stages (faithful to C#) ---------------------------------
    def _order_pallet_by_cancha_method(self, validate_layer, include_top_of_pallet, 
                                       order_pallet_by_product_group, container, products):
        """C#: OrderPalletByCancha - order pallet by cancha/field grouping"""
        # Define order function based on setting
        if self._order_pallet_by_package_code_occupation:
            order_func = lambda prods: sum(p.PercentOccupationIntoDefaultPalletSize for p in prods)
        else:
            order_func = lambda prods: sum(p.Amount for p in prods)

        # Group by GroupCode and order by total (amount or occupation)
        group_by_cancha_products = MountedProductList(products).GroupByGroupCode().OrderByDescending(order_func)

        for same_cancha_products in group_by_cancha_products:
            self._order_pallet(validate_layer, include_top_of_pallet,
                             order_pallet_by_product_group, container, same_cancha_products)

    def _order_pallet(self, validate_layer, include_top_of_pallet,
                      order_pallet_by_product_group, container, products):
        """C#: OrderPallet - main product ordering sequence"""
        self._order_layer_products(validate_layer, container, products)
        self._order_base_products(container, products)
        self._order_chopp(container, products)
        self._order_returnable(order_pallet_by_product_group, container, products)
        self._order_disposable(order_pallet_by_product_group, container, products)
        self._order_isotonic_water(container, products)
        self._order_top_of_pallet(include_top_of_pallet, container, products)
        self._order_marketplace(container, products)

    def _order_marketplace(self, container, products):
        """C#: OrderMarketplace - order marketplace products"""
        self._order_package(container, products)
        self._order_template_box(container, products)

    def _order_package(self, container, products):
        """C#: OrderPackage - order Package marketplace products"""
        package = products.IsPackage()
        self._order_products(container, package)

    def _order_template_box(self, container, products):
        """C#: OrderTemplateBox - order BoxTemplate marketplace products"""
        box_template = products.IsBoxTemplate()
        self._order_products(container, box_template)

    def _order_top_of_pallet(self, include_top_of_pallet, container, products):
        """C#: OrderTopOfPallet - order products that go on top of pallet"""
        top_of_pallet = MountedProductList(products).IsTopOfPallet().NotChopp().NotBasePallet().NotMarketplace()
        if include_top_of_pallet:
            top_of_pallet = MountedProductList(products).IsTopOfPallet().NotChopp()

        self._order_products(container, top_of_pallet)

    def _order_isotonic_water(self, container, products):
        """C#: OrderIsotonicWater - order isotonic water products"""
        isotonic_water = MountedProductList(products).NotMarketplace().IsIsotonicWater().NotTopOfPallet().NotChopp().NotBasePallet()

        if self._order_pallet_by_package_code_occupation:
            self._order_products(container, isotonic_water)
            return

        # Distribute items by amount descending
        for product in isotonic_water.WithoutAssemblySequence().OrderByAmountDesc():
            self._distribute_item(product, isotonic_water, container)

    def _order_disposable(self, order_pallet_by_product_group, container, products):
        """C#: OrderDisposable - order disposable products"""
        disposable = MountedProductList(products).NotMarketplace().NotReturnable().NotTopOfPallet().NotChopp().NotIsotonicWater().NotBasePallet()

        if order_pallet_by_product_group:
            self._order_by_product_group(disposable.WithoutAssemblySequence(), container)
            return

        if self._order_pallet_by_package_code_occupation:
            self._order_products(container, disposable)
            return

        # 3.1 - Group with largest quantity first
        if disposable.WithoutAssemblySequence().Any():
            group_sub_group_disposable = disposable.OrderByAmountDesc()[0].Product.PackingGroup.GroupCode
            disposable_products = MountedProductList([
                p for p in disposable if p.Product.PackingGroup.GroupCode == group_sub_group_disposable
            ])

            for product in disposable_products.WithoutAssemblySequence().OrderByAmountDesc():
                self._distribute_item(product, disposable, container)

        # 3.2 - Remaining groups in order (2, 3, 4, 5)
        remaining = disposable.WithoutAssemblySequence()
        sorted_remaining = sorted(
            remaining,
            key=lambda p: (p.Product.PackingGroup.GroupCode, -p.Amount)
        )
        for product in sorted_remaining:
            self._distribute_item(product, disposable, container)

    def _order_returnable(self, order_pallet_by_product_group, container, products):
        """C#: OrderReturnable - order returnable products"""
        returnable = products.NotMarketplace().IsReturnable().NotTopOfPallet().NotChopp().NotIsotonicWater().NotBasePallet()

        if order_pallet_by_product_group:
            self._order_by_product_group(returnable, container)
            return

        if self._order_pallet_by_package_code_occupation:
            self._order_products(container, returnable)
            return

        for product in returnable.WithoutAssemblySequence().OrderByAmountDesc():
            self._distribute_item(product, returnable, container)

    def _order_chopp(self, container, products):
        """C#: OrderChopp - order chopp (draft beer barrel) products"""
        chopp = MountedProductList(products).NotMarketplace().IsChopp().NotTopOfPallet().NotIsotonicWater().NotBasePallet()
        self._order_products(container, chopp)

    def _order_base_products(self, container, products):
        """C#: OrderBaseProducts - order base pallet products"""
        base_pallet = MountedProductList(products).IsBasePallet().NotIsotonicWater().NotTopOfPallet()
        self._order_products(container, base_pallet)

    def _order_layer_products(self, validate_layer, container, products):
        """C#: OrderLayerProducts - order layer products"""
        if not validate_layer:
            return

        # First product (returnable first) with largest ballast quantity
        first_layer = MountedProductList(products).ToList()[0]

        # Check if there are products with different ballast quantities
        bigger_ballast = any(
            p.Amount / p.Product.PalletSetting.QuantityBallast != 
            first_layer.Amount / first_layer.Product.PalletSetting.QuantityBallast
            for p in MountedProductList(products).WithoutAssemblySequence()
        )

        if bigger_ballast:
            layer_product = MountedProductList(products).WithoutAssemblySequence().OrderByDescIsReturnableAndLayers().ToList()[0]
            container.IncreaseAssemblySequence(layer_product)

    def _order_by_product_group(self, products, container):
        """C#: OrderByProductGroup - order products grouped by packing group"""
        # Group by GroupCode and calculate total amount
        new_order_group = {}
        for p in products:
            group_code = p.Product.PackingGroup.GroupCode
            if group_code not in new_order_group:
                new_order_group[group_code] = 0
            new_order_group[group_code] += p.Amount

        # Order by amount descending
        sorted_groups = sorted(new_order_group.items(), key=lambda x: x[1], reverse=True)

        for group_code, _ in sorted_groups:
            products_in_package_type = MountedProductList([
                p for p in products.WithoutAssemblySequence() 
                if p.Product.PackingGroup.GroupCode == group_code
            ])

            for product in products_in_package_type.WithAmount().OrderByAmountDesc():
                self._distribute_item(product, products_in_package_type, container)

    def _distribute_item(self, item, item_list, container):
        """C#: DistributeItem - distribute item considering similar items"""
        similar_item_list = self._similar_items(item, item_list)

        for product in similar_item_list.WithoutAssemblySequence().WithAmount():
            self._order_similar_items(container, similar_item_list, product.Product)

    def _similar_items(self, item, item_list):
        """C#: SimilarItems - find items with same group and packing code"""
        similar = [
            p for p in item_list
            if (p.Product.PackingGroup.GroupCode == item.Product.PackingGroup.GroupCode and
                p.Product.PackingGroup.PackingCode == item.Product.PackingGroup.PackingCode)
        ]
        return MountedProductList(similar).OrderByAmountDesc()

    def _order_products(self, container, products):
        """C#: OrderProducts - order products by occupation or amount"""
        if self._order_pallet_by_package_code_occupation:
            for product in MountedProductList(products).WithoutAssemblySequence().WithAmount().OrderByPackageOccupationDescThenByAmountDesc():
                container.IncreaseAssemblySequence(product)
        else:
            for product in MountedProductList(products).WithoutAssemblySequence().WithAmount().OrderByAmountDesc():
                container.IncreaseAssemblySequence(product)

    def _order_similar_items(self, container, similar_item_list, product):
        """C#: OrderSimilarItems - order items with same type code"""
        item_type_list = MountedProductList([
            p for p in similar_item_list
            if (p.Product.PackingGroup.GroupCode == product.PackingGroup.GroupCode and
                p.Product.PackingGroup.PackingCode == product.PackingGroup.PackingCode and
                p.Product.PackingGroup.TypeCode == product.PackingGroup.TypeCode)
        ]).WithoutAssemblySequence().OrderByAmountDesc()

        self._order_products(container, item_type_list)
