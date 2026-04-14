import logging

from ...domain.space_size import SpaceSize
from ...domain.base_rule import BaseRule
from ...domain.context import Context


class RecalculateNonPalletizedProductsRule(BaseRule):
    def __init__(self, factor_converter=None):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self._factor_converter = factor_converter

    def should_execute(self, context: Context, item_predicate=None, mounted_space_predicate=None) -> bool:
        if any(i.amount_remaining for i in context.get_items()):
            return True
        self.logger.debug('Todos os produtos ja foram paletizados. Nao ira executar a regra de recalculo de nao paletizados.')
        return False

    def execute(self, context: Context) -> Context:
        factor = self._factor_converter or getattr(context, 'factor_converter', None)

        for order in context.orders:
            if sum(i.amount_remaining for i in order.items) == 0:
                self.logger.debug(f'Todos os produtos da ordem {order.delivery_order} ja foram paletizados')
                continue

            # C#: context.MountedSpaces.NotKegExclusive().OrderByOccupation().FirstOrDefault()
            mounted = [m for m in getattr(context, 'mounted_spaces', [])
                       if not getattr(m, 'is_keg_exclusive', False) and not getattr(m, 'is_bulk', False)]
            mounted = sorted(mounted, key=lambda x: getattr(x, 'occupation', 0))
            pallet_with_less_occupation = mounted[0] if mounted else None

            if not pallet_with_less_occupation:
                self.logger.debug(f'Nao foi possivel encontrar um palete para alocar os itens da ordem {order.delivery_order}')
                continue

            occupation_in_1x1_boxes = 0
            for item in order.items:
                if factor:
                    # C#: item.Product.Factors.FirstOrDefault(d => d.Size == SpaceSize.Size42)
                    item_factor = next(
                        (f for f in getattr(item.product, 'factors', []) if getattr(f, 'size', None) == SpaceSize.Size42),
                        None
                    )
                    if not item_factor:
                        self.logger.debug(f'Nao existe fator 42 cadastrado para o item {getattr(item, "code", "?")}')
                        continue

                    pallet_setting = getattr(item.product, 'PalletSetting', getattr(item.product, 'pallet_setting', None))
                    occupation_in_1x1_boxes += factor.occupation(
                        item.amount, item_factor, pallet_setting, item,
                        context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
                    )
                else:
                    occupation_in_1x1_boxes += getattr(item, 'amount', 0)

                space = getattr(pallet_with_less_occupation, 'Space', getattr(pallet_with_less_occupation, 'space', None))
                space_size = int(getattr(space, 'Size', getattr(space, 'size', 0))) if space else 0
                ms_occupation = getattr(pallet_with_less_occupation, 'Occupation', getattr(pallet_with_less_occupation, 'occupation', 0))

                # C#: if (occupationIn1x1Boxes <= (int)palletWithLessOccupation.Space.Size - palletWithLessOccupation.Occupation)
                if occupation_in_1x1_boxes <= space_size - ms_occupation:
                    if hasattr(context, 'place_non_palletized_on_occupied'):
                        context.place_non_palletized_on_occupied(order, space)

        return context
