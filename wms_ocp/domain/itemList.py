from ..domain.container_type import ContainerType


class ItemList:
    def __init__(self, items):
        self.items = items

    # --- Amount filtering methods ---
    def with_amount_remaining(self):
        """Filtra itens com quantidade disponível (AmountRemaining > 0)"""
        filtrados = [i for i in self.items if i.HasAmountRemaining()]
        return ItemList(filtrados)

    def without_amount_remaining(self):
        """Filtra itens sem quantidade disponível (AmountRemaining == 0)"""
        filtrados = [i for i in self.items if not i.HasAmountRemaining()]
        return ItemList(filtrados)
    
    def with_detached_amount(self):
        """Filtra itens com quantidade avulsa (DetachedAmount > 0)"""
        filtrados = [i for i in self.items if i.HasDetachedAmount()]
        return ItemList(filtrados)
    
    def with_amount_remaining_or_detached_amount(self):
        """Filtra itens com quantidade restante OU avulsa"""
        filtrados = [i for i in self.items if i.WithAmountRemainingOrDetachedAmount()]
        return ItemList(filtrados)
    
    # --- Type checking methods (Product types) ---
    def is_chopp(self):
        """Filtra itens onde produto é Chopp"""
        filtrados = [i for i in self.items if i.IsChopp()]
        return ItemList(filtrados)

    def not_chopp(self):
        """Filtra itens onde produto NÃO é Chopp"""
        filtrados = [i for i in self.items if i.NotChopp()]
        return ItemList(filtrados)
    
    def is_returnable(self):
        """Filtra itens onde produto é Returnable"""
        filtrados = [i for i in self.items if i.IsReturnable()]
        return ItemList(filtrados)
    
    def not_returnable(self):
        """Filtra itens onde produto NÃO é Returnable"""
        filtrados = [i for i in self.items if not i.IsReturnable()]
        return ItemList(filtrados)
    
    def is_isotonic_water(self):
        """Filtra itens onde produto é IsotonicWater"""
        filtrados = [i for i in self.items if i.IsIsotonicWater()]
        return ItemList(filtrados)
    
    def not_isotonic_water(self):
        """Filtra itens onde produto NÃO é IsotonicWater"""
        filtrados = [i for i in self.items if i.NotIsotonicWater()]
        return ItemList(filtrados)
    
    def is_package(self):
        """Filtra itens onde produto é Package"""
        filtrados = [i for i in self.items if i.IsPackage()]
        return ItemList(filtrados)
    
    def is_box_template(self):
        """Filtra itens onde produto é BoxTemplate"""
        filtrados = [i for i in self.items if i.IsBoxTemplate()]
        return ItemList(filtrados)

    def is_marketplace(self):
        """Filtra itens onde produto é marketplace (Package ou BoxTemplate)"""
        filtrados = [i for i in self.items if not i.NotMarketplace()]
        return ItemList(filtrados)

    def not_marketplace(self):
        """Filtra itens onde produto NÃO é marketplace"""
        filtrados = [i for i in self.items if i.NotMarketplace()]
        return ItemList(filtrados)
    
    # --- Palletization methods ---
    def can_be_palletized(self):
        """Filtra itens onde produto pode ser paletizado"""
        filtrados = [i for i in self.items if i.CanBePalletized()]
        return ItemList(filtrados)
    
    def not_can_be_palletized(self):
        """Filtra itens onde produto NÃO pode ser paletizado"""
        filtrados = [i for i in self.items if not i.CanBePalletized()]
        return ItemList(filtrados)
    
    # --- Layer code methods ---
    def with_layer_code(self):
        """Filtra itens com LayerCode > 0"""
        filtrados = [i for i in self.items if i.WithLayerCode()]
        return ItemList(filtrados)
    
    def without_layer_code(self):
        """Filtra itens com LayerCode == 0"""
        filtrados = [i for i in self.items if i.WithoutLayerCode()]
        return ItemList(filtrados)
    
    def layer_code(self, code):
        """Filtra itens com layer_code igual ao valor informado"""
        filtrados = [i for i in self.items if getattr(i.Product, 'LayerCode', None) == code]
        return ItemList(filtrados)
    
    def getByCodeItem(self, code):
        """Filtra itens com layer_code igual ao valor informado"""
        filtrados = [i for i in self.items if getattr(i.Product, 'Code', None) == code]
        return ItemList(filtrados)
    
    # --- Configuration methods ---
    def with_configuration(self, include_top_of_pallet: bool):
        """Filtra itens com configuração específica de topo de palete"""
        filtrados = [i for i in self.items if i.WithConfiguration(include_top_of_pallet)]
        return ItemList(filtrados)
    
    def with_calculate_additional_occupation(self):
        """Filtra itens com CalculateAdditionalOccupation habilitado"""
        filtrados = [i for i in self.items if i.WithCalculateAdditionalOccupation()]
        return ItemList(filtrados)
    
    # --- Ordering methods ---
    def ordered_by_priority_and_amount(self):
        """Ordena por BulkPriority DESC, então Amount DESC"""
        sorted_items = sorted(
            self.items,
            key=lambda x: (
                -(x.Product.PalletSetting.BulkPriority if x.Product and x.Product.PalletSetting else 0),
                -x.Amount
            )
        )
        return ItemList(sorted_items)
    
    def ordered_by_priority_and_amount_remaining(self):
        """Ordena por BulkPriority DESC, então AmountRemaining DESC"""
        sorted_items = sorted(
            self.items,
            key=lambda x: (
                -(x.Product.PalletSetting.BulkPriority if x.Product and x.Product.PalletSetting else 0),
                -x.AmountRemaining
            )
        )
        return ItemList(sorted_items)
    
    def ordered_by_amount_remaining_desc(self):
        """Ordena por AmountRemaining DESC"""
        sorted_items = sorted(self.items, key=lambda x: -x.AmountRemaining)
        return ItemList(sorted_items)

    #temporario
    # def ordered_by_amount_remaining_desc(self):
    #     """Ordena por AmountRemaining DESC"""
    #     # Tie-breaker: when AmountRemaining is equal, order by product code to be deterministic
    #     def key(x):
    #         amt = getattr(x, 'AmountRemaining', 0) or 0
    #         code = getattr(getattr(x, 'Product', None), 'Code', '') or ''
    #         return (-amt, code)

    #     sorted_items = sorted(self.items, key=key)
    #     return ItemList(sorted_items)
    #temporario
    def order_by_amount_desc(self):
        """Ordena por Amount DESC"""
        sorted_items = sorted(self.items, key=lambda x: x.Amount if getattr(x, 'Amount', None) is not None else getattr(x, 'amount', 0), reverse=True)
        return ItemList(sorted_items)

    def order_by_desc_is_returnable_and_layers(self):
        """Ordena desc por (not IsReturnable) e por Amount/QuantityBallast (desc).

        Implements parity with MountedProductList.OrderByDescIsReturnableAndLayers.
        """
        def key(x):
            try:
                prod = getattr(x, 'Product', None)
                is_returnable = False
                if prod is not None:
                    is_returnable = (prod.is_returnable() if callable(getattr(prod, 'is_returnable', None)) else False)

                primary = not bool(is_returnable)

                # compute QuantityBallast fallback
                try:
                    qty_ballast_obj = getattr(prod, 'PalletSetting', None)
                    if qty_ballast_obj is not None:
                        q = getattr(qty_ballast_obj, 'QuantityBallast', getattr(qty_ballast_obj, 'quantity_ballast', None))
                        q = float(q) if q not in (None, 0) else 1.0
                    else:
                        q = 1.0
                except Exception:
                    q = 1.0

                amt = float(getattr(x, 'Amount', getattr(x, 'amount', 0)) or 0)
                secondary = amt / q if q != 0 else amt
                return (primary, secondary)
            except Exception:
                return (False, 0)

        sorted_items = sorted(self.items, key=key, reverse=True)
        return ItemList(sorted_items)
    
    # def ordered_by_returnables_and_group_sub_group(self):
    #     """Ordena por IsReturnable DESC, então GroupAndSubGroup ASC"""
    #     sorted_items = sorted(
    #         self.items,
    #         key=lambda x: (
    #             -int(x.IsReturnable()),
    #             x.Product.GroupAndSubGroup if x.Product else 0
    #         )
    #     )
    #     return ItemList(sorted_items)
    
    def ordered_by_returnables_and_group_sub_group(items):
        return sorted(
            items,
            key=lambda x: (
                0 if x.IsReturnable() else 1,
                x.Product.PackingGroup.GroupCode
                    if x.Product and x.Product.PackingGroup and x.Product.PackingGroup.GroupCode is not None else 0,
                x.Product.PackingGroup.SubGroupCode
                    if x.Product and x.Product.PackingGroup and x.Product.PackingGroup.SubGroupCode is not None else 0
            )
        )

    # --- Generic filtering ---
    def matching(self, predicate):
        """Aplica uma função de filtro genérica"""
        if predicate:
            filtrados = [i for i in self.items if predicate(i)]
            return ItemList(filtrados)
        return self

    # def IsDisposable(self):
    #     """Filtra itens onde produto é Disposable"""
    #     filtrados = [i for i in self.items if i.IsDisposable()]
        # return ItemList(filtrados)

    def is_disposable(self):
        """Alias snake_case para IsDisposable"""
        return self.isDisposable()

    def isDisposable(self):
        """Alias camelCase para IsDisposable"""
        filtrados = [i for i in self.items if i.isDisposable()]
        return ItemList(filtrados)

    def NotDisposable(self):
        """Filtra itens onde produto NÃO é Disposable"""
        filtrados = [i for i in self.items if not i.isDisposable()]
        return ItemList(filtrados)

    def not_disposable(self):
        """Alias snake_case para NotDisposable"""
        return self.NotDisposable()

    def notDisposable(self):
        """Alias camelCase para NotDisposable"""
        return self.NotDisposable()

    def OrderBy(self, key_func):
        """
        Ordena os items pela função key (ordem crescente).
        Port do C# OrderBy - permite encadeamento com ThenBy/ThenByDescending.
        
        Args:
            key_func: Função que extrai a chave de ordenação de cada item
            
        Returns:
            ItemList: Nova lista ordenada (permite encadeamento)
            
        Example:
            items.OrderBy(lambda x: x.Priority)
            items.OrderBy(lambda x: isinstance(x.Product, DisposableProduct))
        """
        sorted_items = sorted(self.items, key=key_func)
        result = ItemList(sorted_items)
        result._sort_keys = [(key_func, False)]  # False = ascending
        return result


    def OrderByDescending(self, key_func):
        """
        Ordena os items pela função key (ordem decrescente).
        Port do C# OrderByDescending.
        
        Args:
            key_func: Função que extrai a chave de ordenação de cada item
            
        Returns:
            ItemList: Nova lista ordenada (permite encadeamento)
            
        Example:
            items.OrderByDescending(lambda x: x.AmountRemaining)
        """
        sorted_items = sorted(self.items, key=key_func, reverse=True)
        result = ItemList(sorted_items)
        result._sort_keys = [(key_func, True)]  # True = descending
        return result


    def ThenBy(self, key_func):
        """
        Adiciona ordenação secundária (ordem crescente).
        Port do C# ThenBy - usa após OrderBy/OrderByDescending.
        
        Args:
            key_func: Função que extrai a chave de ordenação secundária
            
        Returns:
            ItemList: Nova lista ordenada
            
        Example:
            items.OrderBy(lambda x: x.Priority).ThenBy(lambda x: x.Code)
        """
        if not hasattr(self, '_sort_keys'):
            self._sort_keys = []
        
        self._sort_keys.append((key_func, False))
        
        # Cria função de ordenação composta
        def compound_key(item):
            return tuple(func(item) for func, _ in self._sort_keys)
        
        # Ordena considerando todas as chaves e suas direções
        sorted_items = sorted(
            self.items,
            key=compound_key,
            reverse=False  # A direção será controlada pelos valores das chaves
        )
        
        # Para reverter apenas algumas chaves, precisamos de lógica especial
        if any(desc for _, desc in self._sort_keys):
            from functools import cmp_to_key
            
            def compare(item1, item2):
                for func, descending in self._sort_keys:
                    val1, val2 = func(item1), func(item2)
                    if val1 < val2:
                        return 1 if descending else -1
                    elif val1 > val2:
                        return -1 if descending else 1
                return 0
            
            sorted_items = sorted(self.items, key=cmp_to_key(compare))
        
        result = ItemList(sorted_items)
        result._sort_keys = self._sort_keys.copy()
        return result

    def ThenByDescending(self, key_func):
        """
        Adiciona ordenação secundária (ordem decrescente).
        Port do C# ThenByDescending - usa após OrderBy/OrderByDescending.
        
        Args:
            key_func: Função que extrai a chave de ordenação secundária
            
        Returns:
            ItemList: Nova lista ordenada
            
        Example:
            items.OrderBy(lambda x: isinstance(x.Product, DisposableProduct))
                .ThenByDescending(lambda x: x.LayersRemaining)
        """
        if not hasattr(self, '_sort_keys'):
            self._sort_keys = []
        
        self._sort_keys.append((key_func, True))
        
        # Usa mesma lógica do ThenBy com suporte a múltiplas direções
        from functools import cmp_to_key
        
        def compare(item1, item2):
            for func, descending in self._sort_keys:
                val1, val2 = func(item1), func(item2)
                if val1 < val2:
                    return 1 if descending else -1
                elif val1 > val2:
                    return -1 if descending else 1
            return 0
        
        sorted_items = sorted(self.items, key=cmp_to_key(compare))
        
        result = ItemList(sorted_items)
        result._sort_keys = self._sort_keys.copy()
        return result

    def First(self, predicate=None):
        """
        Return the first item. If predicate is provided, return the first item
        matching the predicate. Mirrors C# First (raises on no match).
        """
        if predicate is None:
            if not self.items:
                raise IndexError("First from empty ItemList")
            return self.items[0]

        for it in self.items:
            try:
                if predicate(it):
                    return it
            except Exception:
                # ignore predicate errors and keep searching
                continue

        raise ValueError("No element satisfies the predicate in ItemList")

    # snake_case / aliases
    first = First

    # --- Utility methods ---
    def any(self):
        """Retorna True se houver algum item"""
        return len(self.items) > 0

    def count(self):
        """Quantidade de itens"""
        return len(self.items)
    
    def to_list(self):
        """Converte para lista Python nativa"""
        return list(self.items)

    def __iter__(self):
        """Permite iterar normalmente"""
        return iter(self.items)
    
    def __len__(self):
        """Permite usar len()"""
        return len(self.items)

    def __repr__(self):
        return f"<ItemList: {len(self.items)} items>"
    
    # --- PascalCase aliases for C# compatibility ---
    WithAmountRemaining = with_amount_remaining
    WithoutAmountRemaining = without_amount_remaining
    WithDetachedAmount = with_detached_amount
    WithAmountRemainingOrDetachedAmount = with_amount_remaining_or_detached_amount
    IsChopp = is_chopp
    NotChopp = not_chopp
    IsReturnable = is_returnable
    NotReturnable = not_returnable
    IsIsotonicWater = is_isotonic_water
    NotIsotonicWater = not_isotonic_water
    IsPackage = is_package
    IsBoxTemplate = is_box_template
    IsMarketplace = is_marketplace
    NotMarketplace = not_marketplace
    CanBePalletized = can_be_palletized
    NotCanBePalletized = not_can_be_palletized
    WithLayerCode = with_layer_code
    WithoutLayerCode = without_layer_code
    LayerCode = layer_code
    WithConfiguration = with_configuration
    WithCalculateAdditionalOccupation = with_calculate_additional_occupation
    OrderedByPriorityAndAmount = ordered_by_priority_and_amount
    OrderedByPriorityAndAmountRemaining = ordered_by_priority_and_amount_remaining
    OrderedByAmountRemainingDesc = ordered_by_amount_remaining_desc
    OrderedByReturnablesAndGroupSubGroup = ordered_by_returnables_and_group_sub_group
    Matching = matching
    Any = any
    Count = count
    ToList = to_list
    IsDisposable = is_disposable 
    NotDisposable = not_disposable
    order_by = OrderBy
    order_by_descending = OrderByDescending
    then_by = ThenBy
    then_by_descending = ThenByDescending
    # New methods parity with MountedProductList / C# extensions
    OrderByAmountDesc = order_by_amount_desc
    OrderByDescIsReturnableAndLayers = order_by_desc_is_returnable_and_layers
    WithoutAssemblySequence = lambda self: ItemList([i for i in self.items if getattr(i, 'AssemblySequence', 0) == 0])
    WithoutAssemblySequence = WithoutAssemblySequence
    IsTopOfPallet = lambda self: ItemList([i for i in self.items if getattr(i, 'Product', None) and getattr(i.Product, 'PalletSetting', None) and getattr(i.Product.PalletSetting, 'IncludeTopOfPallet', False)])
    NotTopOfPallet = lambda self: ItemList([i for i in self.items if not (getattr(i, 'Product', None) and getattr(i.Product, 'PalletSetting', None) and getattr(i.Product.PalletSetting, 'IncludeTopOfPallet', False))])
    IsBasePallet = lambda self: ItemList([i for i in self.items if getattr(i, 'Product', None) and getattr(i.Product, 'PalletSetting', None) and getattr(i.Product.PalletSetting, 'BasePallet', False)])
    NotBasePallet = lambda self: ItemList([i for i in self.items if not (getattr(i, 'Product', None) and getattr(i.Product, 'PalletSetting', None) and getattr(i.Product.PalletSetting, 'BasePallet', False))])
  
