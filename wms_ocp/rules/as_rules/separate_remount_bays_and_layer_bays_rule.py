import logging
from ...domain.base_rule import BaseRule
from ...domain.context import Context


class SeparateRemountBaysAndLayerBaysRule(BaseRule):
    def __init__(self, factor_converter=None, mounted_space_operations=None):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self._factor_converter = factor_converter
        self._mounted_space_operations = mounted_space_operations

    def execute(self, context: Context) -> Context:
        self.logger.debug('Iniciando execucao da regra SeparateRemountBaysAndLayerBaysRule')
        self._separate_remount_bays(context)
        self._separate_layer_bays(context)
        return context

    def _separate_remount_bays(self, context: Context):
        self.logger.debug('Iniciando tentativa de separar as baias de remonte')

        if getattr(context, 'is_crossdocking', False):
            self.logger.debug('Ignorando execucao da regra para paletizacao de crossdocking')
            return

        if not getattr(context, 'spaces', None):
            self.logger.debug('Nao ha baias vazias no caminhao')
            return

        remount_not_layer = [m for m in getattr(context, 'mounted_spaces', []) if getattr(m, 'is_remount', False) and not getattr(m, 'is_layer', False)]
        if not remount_not_layer:
            self.logger.debug('Nao ha paletes de remonte nao layer para separar')
            return

        for remount in remount_not_layer:
            remount_pallet = remount.get_first_pallet() if hasattr(remount, 'get_first_pallet') else None
            disposable_mounted_products = [p for p in getattr(remount_pallet, 'products', []) if p.is_chopp() or p.is_isotonic_water() or p.is_disposable_not_top_pallet()]

            if not disposable_mounted_products:
                self.logger.debug(f'Nao foram encontrados produtos para mover no palete {getattr(remount, "number", "?")}/{getattr(remount, "side", "?")}')
                continue

            empty_space = context.spaces[0] if context.spaces else None
            if not empty_space:
                self.logger.debug('Nao ha mais baias vazias no caminhao')
                break

            # C#: _factorConverter.Occupation(x, emptySpace.Size, x.Item, ...)
            empty_size = getattr(empty_space, 'size', getattr(empty_space, 'Size', 0))
            if self._factor_converter:
                occupation_needed_to_move = sum(
                    self._factor_converter.occupation(
                        x, empty_size,
                        getattr(x, 'Item', getattr(x, 'item', None)),
                        context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
                    )
                    for x in disposable_mounted_products
                )
            else:
                occupation_needed_to_move = sum(getattr(x, 'estimated_occupation', 0) for x in disposable_mounted_products)

            if float(empty_size) < float(occupation_needed_to_move):
                self.logger.debug('Os produtos selecionados nao cabem no espaco vazio')
                continue

            # C#: _mountedSpaceOperations.MoveMountedProducts(...)
            ops = self._mounted_space_operations or context.domain_operations
            ops.move_mounted_products(context, empty_space, remount, disposable_mounted_products)

            # set new base product if available
            if hasattr(remount_pallet, 'products') and remount_pallet.products:
                new_product_base = sorted(remount_pallet.products, key=lambda x: getattr(x, 'first_layer_index', 0))[0]
                if new_product_base and hasattr(remount_pallet, 'set_product_base'):
                    remount_pallet.set_product_base(new_product_base.product)

            if not context.spaces:
                self.logger.debug('Nao ha mais baias vazias no caminhao')
                break

    def _separate_layer_bays(self, context: Context):
        self.logger.debug('Iniciando tentativa de separar as baias de Layer')
        layer_with_not_layer = [m for m in getattr(context, 'mounted_spaces', []) if getattr(m, 'is_layer', False) and any(not p.is_layer() for p in getattr(m.get_first_pallet(), 'products', []))]
        if not layer_with_not_layer:
            self.logger.debug('Nao ha paletes layer com produtos nao layer')
            return

        for layer in layer_with_not_layer:
            self._try_move_notlayer_mounted_products(context, layer)

    def _try_move_notlayer_mounted_products(self, context: Context, layer_mounted_space):
        not_layer_mounted_products = layer_mounted_space.get_first_pallet().products_not_layer() if hasattr(layer_mounted_space.get_first_pallet(), 'products_not_layer') else []
        disposable = [p for p in not_layer_mounted_products if p.is_disposable_product()]
        returnable = [p for p in not_layer_mounted_products if p.is_returnable()]

        self._try_move_mounted_products(context, layer_mounted_space, disposable)
        self._try_move_mounted_products(context, layer_mounted_space, returnable)

    def _try_move_mounted_products(self, context: Context, source_mounted_space, source_mounted_products):
        used_spaces = []
        for mounted_product in list(source_mounted_products):
            # C#: _factorConverter.Occupation(mountedProduct, sourceMountedSpace.Space.Size, mountedProduct.Item, ...)
            source_size = getattr(getattr(source_mounted_space, 'space', source_mounted_space), 'size', 0)
            if self._factor_converter:
                source_occupation = self._factor_converter.occupation(
                    mounted_product, source_size,
                    getattr(mounted_product, 'Item', getattr(mounted_product, 'item', None)),
                    context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
                )
            else:
                source_occupation = getattr(mounted_product, 'estimated_occupation', 0)
            target_space = None

            # Try same order mounted space with same type and occupation remaining
            available = [m for m in getattr(context, 'mounted_spaces', []) if getattr(m, 'container_type', None) == getattr(mounted_product.product, 'container_type', None) and not getattr(m, 'is_layer', False) and getattr(m, 'has_space_and_not_blocked', lambda: True)()]

            same_order = next((m for m in available if getattr(m, 'order_identifier', None) == getattr(mounted_product.order, 'identifier', None)), None)
            if same_order:
                target_space = same_order.space if hasattr(same_order, 'space') else same_order
            else:
                empty_space = next((s for s in getattr(context, 'spaces', []) if getattr(s, 'occupation', 0) >= source_occupation), None)
                if empty_space:
                    target_space = empty_space
                else:
                    any_order_mounted = available[0] if available else None
                    target_space = any_order_mounted.space if any_order_mounted and hasattr(any_order_mounted, 'space') else (any_order_mounted if any_order_mounted else None)

            if not target_space:
                self.logger.debug(f'Nao foi encontrado um palete de destino para mover o item {getattr(mounted_product.product, "code", "?")}, da baia {getattr(source_mounted_space, "number", "?")}/{getattr(source_mounted_space, "side", "?")}')
                continue

            # C#: _mountedSpaceOperations.MoveMountedProduct(...)
            ops = self._mounted_space_operations or context.domain_operations
            moved_succeed = ops.move_mounted_product(context, target_space, source_mounted_space, mounted_product)

            if moved_succeed and target_space not in used_spaces:
                used_spaces.append(target_space)
