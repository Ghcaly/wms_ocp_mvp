from ...domain.base_rule import BaseRule
from ...domain.context import Context


class RecalculatePalletOccupationRule(BaseRule):
    def __init__(self, factor_converter=None):
        super().__init__(name='RecalculatePalletOccupationRule')
        self._factor_converter = factor_converter

    def execute(self, context: Context) -> Context:
        factor = self._factor_converter or getattr(context, 'factor_converter', None)

        # C#: foreach (var mountedSpace in context.MountedSpaces.NotBulk())
        for ms in getattr(context, 'mounted_spaces', []) or []:
            if getattr(ms, 'is_bulk', False):
                continue

            ms.SetOccupation(0)

            # C#: foreach (var pallet in mountedSpace.Containers.OfType<IPallet>())
            for container in getattr(ms, 'containers', []) or []:
                # Filter to pallet-type containers only (C#: OfType<IPallet>())
                if not getattr(container, 'is_pallet', True):
                    continue

                for mounted_product in getattr(container, 'products', []) or []:
                    # C#: var factor = mountedProduct.Product?.Factors.FirstOrDefault(d => d.Size == mountedSpace.Space.Size)
                    product = getattr(mounted_product, 'Product', getattr(mounted_product, 'product', None))
                    space_size = getattr(getattr(ms, 'Space', getattr(ms, 'space', None)), 'Size',
                                        getattr(getattr(ms, 'Space', getattr(ms, 'space', None)), 'size', None))
                    factor_obj = None
                    if product is not None:
                        factors = getattr(product, 'Factors', getattr(product, 'factors', []))
                        factor_obj = next((f for f in factors if getattr(f, 'Size', getattr(f, 'size', None)) == space_size), None)

                    item = getattr(mounted_product, 'Item', getattr(mounted_product, 'item', None))
                    pallet_setting = getattr(product, 'PalletSetting', getattr(product, 'pallet_setting', None)) if product else None
                    amount = getattr(mounted_product, 'Amount', getattr(mounted_product, 'amount', 0))

                    # C#: _factorConverter.Occupation(mountedProduct.Amount, factor, mountedProduct.Product.PalletSetting, mountedProduct.Item, ...)
                    try:
                        total_occupation = factor.occupation(
                            amount, factor_obj, pallet_setting, item,
                            context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
                        )
                    except Exception:
                        total_occupation = 0

                    # C#: var productOccupation = totalOccupation - mountedProduct.Item.AdditionalOccupation
                    additional_occupation = getattr(item, 'AdditionalOccupation', getattr(item, 'additional_occupation', 0)) if item else 0
                    product_occupation = total_occupation - additional_occupation

                    # C#: mountedProduct.SetOccupation(productOccupation)
                    if hasattr(mounted_product, 'SetOccupation'):
                        mounted_product.SetOccupation(product_occupation)
                    else:
                        setattr(mounted_product, 'occupation', product_occupation)

                    # C#: mountedSpace.IncreaseOccupation(totalOccupation)
                    if hasattr(ms, 'IncreaseOccupation'):
                        ms.IncreaseOccupation(total_occupation)
                    else:
                        ms.occupation = getattr(ms, 'occupation', 0) + total_occupation

        return context
