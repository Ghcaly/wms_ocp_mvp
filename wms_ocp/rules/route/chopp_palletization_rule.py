"""
Regra de paletização de Chopp (barris de cerveja).
Port fiel do C# ChoppPalletizationRule.
"""
from decimal import Decimal

from ...domain.subsequences import SubsequenceGenerator
from ...domain.base_rule import BaseRule
from ...domain.itemList import ItemList
from typing import List, Dict, Callable
import math


class ItemsWithSamePalletDozenDto:
    """DTO para agrupar itens com mesma configuração de dúzia de palete."""
    
    def __init__(self, quantity_dozen: int, items: List, occupation_by_space_size: Dict[int, float]):
        self.quantity_dozen = quantity_dozen
        self.items = items
        self.occupation_by_space_size = occupation_by_space_size


class ChoppPalletizationRule(BaseRule):
    """
    Regra para paletização de produtos do tipo Chopp (barris).
    
    Estratégia de paletização:
    1. Tentar criar paletes fechados em baias vazias
    2. Agrupar chopes de mesma litragem que caibam juntos
    3. Adicionar chopes restantes em baias vazias
    4. Adicionar chopes restantes em baias já montadas
    5. Processar configurações especiais (KegExclusivePallet)
    """

    def __init__(self, factor_converter=None):
        super().__init__(name='ChoppPalletizationRule')
        self._factor_converter = factor_converter
        self._complex_customer = None
        self._without_group_limit = False

    def with_complex_customer(self, complex_customer: int):
        """Configura cliente complexo para paletização especial."""
        self._complex_customer = complex_customer
        return self

    def without_group_limit(self):
        """Remove limite de agrupamento."""
        self._without_group_limit = True
        return self

    @staticmethod
    def _get_items_chopp(context, item_predicate: Callable = lambda x: True):
        """
        Obtém itens do tipo Chopp que podem ser paletizados.
        
        C#: context.GetItems().Where(itemPredicate).IsChopp().WithAmountRemaining().WithoutLayerCode()
        """
        items_list = ItemList(context.get_items())
        return (items_list
                .matching(item_predicate)
                .is_chopp()
                .with_amount_remaining()
                .without_layer_code())

    def should_execute(self, context, item_predicate: Callable = lambda x: True, mounted_space_predicate=None) -> bool:
        """Verifica se existem itens chopp para paletizar."""
        items_chopp = self._get_items_chopp(context, item_predicate)
        
        if items_chopp.any():
            return True
        
        context.add_execution_log("Nao foram encontrados items chope para paletizar")
        return False

    def execute(self, context, item_predicate: Callable = lambda x: True, mounted_space_predicate=None):
        """Executa a paletização de chopp."""
        chopp_to_palletization = self._get_items_chopp(context, item_predicate)
        
        context.add_execution_log(f"Iniciando o processamento {len(chopp_to_palletization)} itens de chope sem layer code na regra de paletização chope")
        
        # Agrupa itens por configuração de palete dúzia
        list_of_items_with_same_pallet_dozen_config = self._get_items_with_same_pallet_dozen(
            chopp_to_palletization, 
            context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
        )
        
        context.add_execution_log(f"Chopes agrupados em {len(list_of_items_with_same_pallet_dozen_config)} grupos com base na sua configuração de palete dúzia")
        
        # Executa estratégias de paletização em ordem
        self._palletization_chopp_to_closed_pallet_into_empty_spaces(context, list_of_items_with_same_pallet_dozen_config)
        self._palletization_chopp_that_more_items_with_same_liter_into_empty_spaces(context, list_of_items_with_same_pallet_dozen_config)
        self._palletization_chopp_with_more_amount_remaining_into_empty_spaces(context, list_of_items_with_same_pallet_dozen_config)
        self._palletization_remaining_chopp_into_mounted_spaces(context, list_of_items_with_same_pallet_dozen_config)
        self._keg_exclusive_pallet_process(context)

    def _get_items_with_same_pallet_dozen(self, chopp_items, calculate_additional_occupation: bool) -> List[ItemsWithSamePalletDozenDto]:
        """
        Agrupa itens chopp por quantidade dúzia e calcula ocupação por tamanho de espaço.
        
        C#: choppToPalletization.GroupBy(x => x.Product.PalletSetting.QuantityDozen)
        """
        # Agrupa por quantity_dozen
        groups_dict = {}
        for item in chopp_items:
            qty_dozen = item.Product.PalletSetting.QuantityDozen
            groups_dict.setdefault(qty_dozen, []).append(item)
        
        result = []
        for qty_dozen, items in groups_dict.items():
            # Calcula ocupação para cada tamanho de espaço
            # Size42 usa soma de todos os itens, demais usam primeiro item
            occupation_by_size = {
                42: self._factor_converter.occupation(
                    sum(i.AmountRemaining for i in items), 
                    Decimal(42), 
                    items[0], 
                    calculate_additional_occupation
                ),
                28: self._factor_converter.occupation(items[0].AmountRemaining, Decimal(28), items[0], calculate_additional_occupation),
                21: self._factor_converter.occupation(items[0].AmountRemaining, Decimal(21), items[0], calculate_additional_occupation),
                14: self._factor_converter.occupation(items[0].AmountRemaining, Decimal(14), items[0], calculate_additional_occupation),
            }
            
            dto = ItemsWithSamePalletDozenDto(qty_dozen, items, occupation_by_size)
            result.append(dto)
        
        return result

    def _palletization_chopp_to_closed_pallet_into_empty_spaces(self, context, list_of_items_with_same_pallet_dozen_config):
        """
        Tenta adicionar chopes como paletes fechados em baias vazias.
        Ordena grupos por quantidade total decrescente.
        """
        print("Iniciando tentativa de adicionar os chopes como paletes fechados")
        
        # Ordena grupos por soma de amount_remaining decrescente
        sorted_groups = sorted(
            list_of_items_with_same_pallet_dozen_config,
            key=lambda g: sum(i.AmountRemaining for i in g.items),
            reverse=True
        )
        
        for items_with_same_pallet_dozen_config in sorted_groups:
            context.add_execution_log(f"Processando agrupamento palete dúzia {items_with_same_pallet_dozen_config.quantity_dozen}")

            # Ordena espaços vazios por número decrescente, depois Side DESC (M=77 antes de A=65)
            for empty_space in sorted(context.spaces, key=lambda s: (-getattr(s, 'Number', 0), int(str(getattr(s, 'Side', 65) or 65).strip() or 65))):
                self._process_closed_chopp_palletization(context, items_with_same_pallet_dozen_config, empty_space)

    def _palletization_chopp_that_more_items_with_same_liter_into_empty_spaces(self, context, list_of_items_with_same_pallet_dozen_config):
        """
        Tenta adicionar juntos chopes de mesma litragem que caibam na baia vazia.
        Usa subsequências para encontrar melhor combinação.
        """
        for empty_space in sorted(context.spaces, key=lambda s: (-getattr(s, 'Number', 0), int(str(getattr(s, 'Side', 65) or 65).strip() or 65))):
            print(f"Iniciando tentativa de adicionar juntos os chopes de mesma litragem que caibam na baia {empty_space.Number} vazia")
            
            # Gera subsequências e filtra as que cabem no espaço
            # subsequences = self._generate_subsequences(list_of_items_with_same_pallet_dozen_config)#temporario 1812
            subsequences = list(SubsequenceGenerator(limit=30000).subsequences(list_of_items_with_same_pallet_dozen_config))
            sequences_that_fit = [
                seq for seq in subsequences
                if sum(g.occupation_by_space_size.get(empty_space.Size, 0) for g in seq) <= empty_space.Size
                and all(any(i.AmountRemaining > 0 for i in g.items) for g in seq)
            ]
            
            # Pega sequência com mais itens
            if sequences_that_fit:
                best_sequence = max(sequences_that_fit, key=len)
                
                if sum(len(g.items) for g in best_sequence) > 1:
                    # Ordena por amount_remaining decrescente e processa
                    for items_config in sorted(best_sequence, key=lambda g: sum(i.AmountRemaining for i in g.items), reverse=True):
                        self._process_chopp_palletization(context, items_config, empty_space)

    def _palletization_chopp_with_more_amount_remaining_into_empty_spaces(self, context, list_of_items_with_same_pallet_dozen_config):
        """Adiciona chopes restantes em baias vazias, priorizando maior quantidade."""
        sorted_groups = sorted(
            list_of_items_with_same_pallet_dozen_config,
            key=lambda g: sum(i.AmountRemaining for i in g.items),
            reverse=True
        )
        
        for items_with_same_pallet_dozen_config in sorted_groups:
            for empty_space in sorted(context.spaces, key=lambda s: (-getattr(s, 'Number', 0), int(str(getattr(s, 'Side', 65) or 65).strip() or 65))):
                print(f"Iniciando tentativa de adicionar os chopes restantes na baia {empty_space.Number} vazia")
                self._process_chopp_palletization(context, items_with_same_pallet_dozen_config, empty_space)

    def _palletization_remaining_chopp_into_mounted_spaces(self, context, list_of_items_with_same_pallet_dozen_config):
        """Adiciona chopes restantes em baias já montadas que tenham espaço."""
        sorted_groups = sorted(
            list_of_items_with_same_pallet_dozen_config,
            key=lambda g: sum(i.AmountRemaining for i in g.items),
            reverse=True
        )
        
        for items_with_same_pallet_dozen_config in sorted_groups:
            # Filtra mounted_spaces que são chopp e têm espaço e não estão bloqueados
            chopp_mounted_spaces = [ms for ms in context.mounted_spaces if ms.IsChopp() and ms.HasSpaceAndNotBlocked()]
            
            for mounted_space in chopp_mounted_spaces:
                space = mounted_space.Space
                print(f"Iniciando tentativa de adicionar os chopes restantes na baia {space.Number} não vazia")
                self._process_chopp_palletization(context, items_with_same_pallet_dozen_config, space)

    def _keg_exclusive_pallet_process(self, context):
        """
        Processa configuração de pallet exclusivo para barris (KEG).
        Bloqueia mounted_spaces de chopp e marca containers como KegExclusive.
        """
        if not context.get_setting('KegExclusivePallet', False):
            return
        
        chopp_mounted_spaces = [ms for ms in context.mounted_spaces if ms.IsChopp()]
        
        for mounted_space in chopp_mounted_spaces:
            mounted_space.Block()
            
            # Marca pallets de chopp como KegExclusive
            for container in mounted_space.Containers:
                if container.IsTypeBaseChopp():
                    container.SetKegExclusive()

    def _process_closed_chopp_palletization(self, context, items_with_same_pallet_dozen_config: ItemsWithSamePalletDozenDto, empty_space):
        """
        Processa paletização de chopp como pallet fechado.
        Verifica se o item ocupa o espaço completo.
        """
        space_size_to_calculation = empty_space.Size
        
        # Ordena itens por amount_remaining decrescente
        sorted_items = sorted(items_with_same_pallet_dozen_config.items, key=lambda i: i.AmountRemaining, reverse=True)
        
        for item in sorted_items:
            if item.AmountRemaining == 0:
                continue
            
            # Calcula ocupação do item
            item_occupation = self._factor_converter.occupation(
                item.AmountRemaining,
                space_size_to_calculation,
                item,
                context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
            )
            
            # Se não ocupa o espaço completo, pula
            if item_occupation < space_size_to_calculation:
                continue
            
            # Calcula quantidade que cabe no espaço
            amount_of_items_by_occupation = int(math.floor(
                self._factor_converter.quantity(
                    space_size_to_calculation,
                    item.Product.GetFactor(space_size_to_calculation),
                    item.Product.PalletSetting
                )
            ))
            
            if amount_of_items_by_occupation <= 0:
                continue
            
            # Verifica se pode adicionar
            if not context.domain_operations.can_add(context, empty_space, item, amount_of_items_by_occupation, self._without_group_limit):
                continue
            
            # Calcula ocupação pela quantidade máxima
            occupation_by_max_amount = self._factor_converter.occupation(
                amount_of_items_by_occupation,
                empty_space.Size,
                item,
                context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
            )
            
            # Adiciona produto
            mounted_space = self._add_product(
                context,
                item,
                empty_space,
                empty_space.Size,
                occupation_by_max_amount,
                amount_of_items_by_occupation
            )
            
            context.add_execution_log(
                f"Adicionado palet fechado de chopp. Baia {empty_space.Number} / {empty_space.sideDesc}, "
                f"com {amount_of_items_by_occupation} {item.Product.Name}, ocupacao {mounted_space.Occupation}"
            )
            break

    def _process_chopp_palletization(self, context, items_with_same_pallet_dozen_config: ItemsWithSamePalletDozenDto, space):
        """Processa paletização normal de chopp (não necessariamente fechado)."""
        sorted_items = sorted(items_with_same_pallet_dozen_config.items, key=lambda i: i.AmountRemaining, reverse=True)
        
        for item in sorted_items:
            if item.AmountRemaining == 0:
                continue
            
            # Verifica se pode adicionar
            if not context.domain_operations.can_add(context, space, item, item.AmountRemaining, self._without_group_limit):
                continue
            
            # Calcula ocupação
            item_occupation = self._factor_converter.occupation(
                item.AmountRemaining,
                space.Size,
                item,
                context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
            )
            
            # Adiciona produto
            mounted_space = self._add_product(
                context,
                item,
                space,
                space.Size,
                item_occupation,
                item.AmountRemaining
            )
            
            # Verifica se espaço ficou cheio
            if self._check_if_full_space(space.Size, mounted_space):
                break

    def _add_product(self, context, item, space, space_size_to_calculation, occupation, amount_to_add):
        """
        Adiciona produto ao espaço.
        Suporta cliente complexo se configurado.
        
        C#: context.AddProduct(space, item, amountToAdd, firstLayerIndex, quantityOfLayer, occupation)
        """
        mounted_space = context.get_mounted_space(space)
        first_layer_index = mounted_space.GetNextLayer() if mounted_space else 0
        
        if self._complex_customer is None:
            # C#: context.AddProduct(space, item, amountToAdd, firstLayerIndex, item.Product.GetQuantityOfLayerToSpace(...), occupation)
            mounted_bay = context.AddProduct(
                space,
                item,
                amount_to_add,
                first_layer_index,
                item.Product.GetQuantityOfLayerToSpace(space_size_to_calculation, amount_to_add),
                occupation
            )
        else:
            # C#: context.AddComplexLoadProduct(space, item, amountToAdd, occupation, _complexCustomer.Value)
            mounted_bay = context.AddComplexLoadProduct(
                space,
                item,
                amount_to_add,
                occupation,
                self._complex_customer
            )
        
        context.add_execution_log(
            f"Adicionado o item {item.Product.Name} na baia {space.Number} / {space.sideDesc}, "
            f"na quantidade {amount_to_add} ficando com a ocupacao de {mounted_bay.Occupation}"
        )
        
        return mounted_bay

    def _check_if_full_space(self, space_size_to_calculation, mounted_space) -> bool:
        """
        Verifica se espaço está cheio e configura ballast se necessário.
        Retorna True se cheio.
        """
        if not mounted_space.Full:
            return False
        
        # Encontra primeiro pallet de chopp e configura ballast
        for container in mounted_space.Containers:
            if container.IsTypeBaseChopp():
                ballast_qty = 2 if space_size_to_calculation == 42 else 1
                container.SetBallast(ballast_qty)
                break
        
        return True

    @staticmethod
    def _generate_subsequences(items):
        """
        Gera todas as subsequências possíveis de uma lista.
        Equivalente ao C# Subsequences() extension method.
        """
        n = len(items)
        subsequences = []
        
        # Gera todas as combinações possíveis (2^n - 1, excluindo vazio)
        for i in range(1, 2**n):
            subseq = [items[j] for j in range(n) if (i & (1 << j))]
            subsequences.append(subseq)
        
        return subsequences
