from decimal import Decimal
from typing import Optional

from ...domain.space_size import SpaceSize
from ...domain.space_list import SpaceList
from ...domain.itemList import ItemList
from ...domain.base_rule import BaseRule


class BulkPalletRule(BaseRule):
    
    def __init__(self):
        super().__init__(name="BulkPalletRule")
        self._complex_customer = None

    def with_complex_customer(self, complex_customer: Optional[int]):
        self._complex_customer = complex_customer
        return self

    def execute(self, context, item_predicate=None, mounted_space_predicate=None):
        # collect items and apply optional predicate
        filtered = ItemList(context.get_items()).matching(item_predicate).not_chopp().not_marketplace()\
            .with_amount_remaining()
        
        filtered = context.domain_operations.ordered_by(filtered, fields=["priority", ('amount', 'desc')])
        # items = list(context.get_items() or [])

        context.add_execution_log(f"BulkPalletRule: processing {len(filtered)} items (post-filter)")

        for item in filtered:
            qty_per_pallet = item.Product.PalletSetting.Quantity
            # context.add_execution_log(f"BulkPalletRule: qty_per_pallet for {getattr(item, 'code', '')}: {qty_per_pallet}")

            # iterate configured spaces (empty bays) ordered by size desc then number asc
            # mirrors C#: context.GetEmptySpaces().OrderedBySizeAndNumber()
            bays = SpaceList(context.GetEmptySpaces()).ordered_by_size_and_number()

            # context.add_execution_log(f"Numero de baias do caminhao: {len(list(bays))}")

            for bay in bays:
                self._add_bulk_pallet(context, item, bay)
        
        # context.add_execution_log(
        #         "BulkPalletRule: Execucao da regra de palete fechado finalizada. Chamando a proxima regra."
        #     )

    def _get_bulk_quantity(self, item, factor):
        # mirrors C#: factor.Quantity.HasValue && item.AmountRemaining >= factor.Quantity
        if factor.Quantity is not None and item.amount_remaining >= factor.Quantity:
            return int(factor.Quantity)
        return None

    def _add_bulk_pallet(self, context, item, bay):
        """
        Adiciona palete bulk (fechado).
        Port do método AddBulkPallet do C#.
        """
        try:
            # mirrors C#: item.Product.Factors.First(x => x.Size == bay.Size)
            factor = item.Product.GetFactor(bay.Size)
        except (ValueError, StopIteration):
            return
        
        # Calcula quantidade bulk
        bulk_quantity = self._get_bulk_quantity(item, factor)
        if not bulk_quantity:
            # context.add_execution_log(f"BulkPalletRule: Nenhuma quantidade bulk definida para o item {item.Code} com fator {factor.Quantity} na baia {bay.Number}.")
            return
        
        self._add_bulk_pallet_with_factor(context, item, factor, bay, bulk_quantity)

    def _add_bulk_pallet_with_factor(self, context, item, factor, bay, quantity):
        """
        Adiciona palete bulk com fator específico.
        Port do método AddBulkPallet(context, item, factor, bay, quantity) do C#.
        """
        # Determina se é palete fechado
        is_closed_pallet = (
            bay.Size == SpaceSize.Size42
            or (
                context.get_setting('BulkAllPallets', False) 
                and getattr(factor, 'Quantity', None) == item.Product.PalletSetting.Quantity
            )
        )
        
        not_mount_bulk = context.get_setting('NotMountBulkPallets', False)
        
        if is_closed_pallet or not not_mount_bulk:
            # Adiciona produto no espaço
            mounted_space = self._add_product_into_space(context, item, bay, quantity)
            
            # Marca primeiro palete como bulk se for fechado
            if is_closed_pallet and mounted_space:
                try:
                    first_pallet = mounted_space.GetFirstPallet() if hasattr(mounted_space, 'GetFirstPallet') else mounted_space.get_first_pallet()
                    if hasattr(first_pallet, 'SetBulk'):
                        first_pallet.SetBulk(True)
                    elif hasattr(first_pallet, 'set_bulk'):
                        first_pallet.set_bulk(True)
                except Exception as e:
                    context.add_execution_log(f"Erro ao marcar palete como bulk: {e}")
            
            # Log
            bay_number = getattr(bay, 'Number', getattr(bay, 'number', '?'))
            bay_side = getattr(getattr(bay, 'sideDesc', None), 'name', '') or getattr(bay, 'side', '')
            occupation = getattr(mounted_space, 'Occupation', getattr(mounted_space, 'occupation', 0))
            
            context.add_execution_log(
                f"Pallet adicionado na baia {bay_number} / {bay_side}, "
                f"tamanho {int(bay.Size)} com {quantity} {item.Product.Name}, "
                f"ocupacao {occupation}, fechado:{is_closed_pallet}"
            )
            context.add_execution_log(
                f"{item.AmountRemaining} restantes no contexto de {item.Product.Name} "
                f"depois de adicionar {quantity}"
            )
        else:
            context.add_execution_log(
                f"{item.Code} não será montado palete fechado: {is_closed_pallet} "
                f"e ignorar montagem de palete bulk: {not_mount_bulk}"
            )
            
    def _add_product_into_space(self, context, item, bay, quantity):
        """
        Adiciona produto em um espaço (bay).
        Port do método AddProductIntoSpace do C#.
        
        Args:
            context: Contexto da regra
            item: Item a ser adicionado
            bay: Espaço/baia onde adicionar
            quantity: Quantidade a adicionar
            
        Returns:
            MountedSpace criado
        """
        # Define ocupação adicional como 0
        if hasattr(item, 'SetAdditionalOccupation'):
            item.SetAdditionalOccupation(0)
        elif hasattr(item, 'set_additional_occupation'):
            item.set_additional_occupation(0)
        else:
            item.AdditionalOccupation = 0
        
        # Adiciona produto no espaço
        if self._complex_customer is None:
            mounted_space = context.AddProduct(bay, item, quantity)
        else:
            mounted_space = context.AddComplexLoadProduct(
                bay, 
                item, 
                quantity, 
                float(bay.Size), 
                self._complex_customer
            )
        
        return mounted_space