from typing import Any
from .space import Space
from .mounted_product import MountedProduct
from .mounted_space import MountedSpace
# from .context import Context
from multipledispatch import dispatch
from .factor_converter import FactorConverter

class DomainOperations:
    def __init__(self):
        self._max_groups = None

    def WithMaxGroups(self, max_groups):
        self._max_groups = max_groups

    # multipledispatch-based overloads for CanAdd (faithful to C# signatures)
    @dispatch(object, Space, object, int, bool, bool)
    def CanAdd(self, context: object, space: Space, item: object, quantityToAdd: int, move=False, withoutGroupLimitCheck=False):
        """CanAdd(IRuleContext context, ISpace space, IItem item, int quantityToAdd, bool move = False, bool withoutGroupLimitCheck = False)"""
        return self.can_add_space(context, space, item, quantityToAdd, move, withoutGroupLimitCheck)

    @dispatch(object, Space, object, int)
    def CanAdd(self, context: object, space: Space, item: object, quantityToAdd: int):
        """CanAdd without optional flags: delegate to can_add_space with defaults."""
        return self.can_add_space(context, space, item, quantityToAdd, move=False, withoutGroupLimitCheck=False)

    @dispatch(object, MountedSpace, object, int, bool)
    def CanAdd(self, context: object, mountedSpace: MountedSpace, item: object, quantityToAdd: int, withoutGroupLimitCheck=False):
        """CanAdd(IRuleContext context, IMountedSpace mountedSpace, IItem item, int quantityToAdd, bool withoutGroupLimitCheck = False)"""
        return self.can_add_mounted(context, mountedSpace, item, quantityToAdd, withoutGroupLimitCheck)

    @dispatch(object, MountedSpace, object, int)
    def CanAdd(self, context: object, mountedSpace: MountedSpace, item: object, quantityToAdd: int):
        """CanAdd(IMountedSpace, IItem, int) without optional flag: delegate to can_add_mounted."""
        return self.can_add_mounted(context, mountedSpace, item, quantityToAdd, withoutGroupLimitCheck=False)

    @dispatch(object, MountedSpace, object)
    def CanAdd(self, context: object, mountedSpace: MountedSpace, item: object):
        """CanAdd(IRuleContext context, IMountedSpace mountedSpace, IItem item) -> bool"""
        return self.can_add_basic(context, mountedSpace, item)

    @dispatch(object, MountedSpace, MountedSpace)
    def CanAdd(self, context: object, mountedSpaceToAdd: MountedSpace, mountedSpaceToRemoveItems: MountedSpace):
        """CanAdd(IRouteRuleContext context, IMountedSpace mountedSpaceToAdd, IMountedSpace mountedSpaceToRemoveItems) -> bool"""
        return self.can_add_mounted_to_mounted(context, mountedSpaceToAdd, mountedSpaceToRemoveItems)

    # Pythonic alias that mirrors previous behavior (keeps backward compatibility)
    def can_add(self, *args, **kwargs):
        try:
            return self.CanAdd(*args, **kwargs)
        except Exception:
            # fallback: try existing implementations based on args
            if len(args) >= 4:
                return self.can_add_space(*args, **kwargs)
            if len(args) == 3:
                return self.can_add_basic(*args, **kwargs)
            return False

    # --- implementations ported from ContextActions.cs ---
    def can_add_space(self, context, space, item, quantityToAdd, move=False, withoutGroupLimitCheck=False):
        if (not move and item.AmountRemaining <= 0) or quantityToAdd <= 0:
            return False

        mountedSpace = context.GetMountedSpace(space)
        if mountedSpace is None:
            from .factor_converter import FactorConverter
            occupationToAdd = FactorConverter().occupation(quantityToAdd, space.Size, item, self._check_calculate_additional_occupation(context))
            self._write_log_additional_occupation(context, item, quantityToAdd)
            return occupationToAdd <= int(space.Size)

        return self.can_add_mounted(context, mountedSpace, item, quantityToAdd, withoutGroupLimitCheck)

    def CanAddSpace(self, *args, **kwargs):
        return self.can_add_space(*args, **kwargs)

    def can_add_mounted(self, context, mountedSpace, item, quantityToAdd, withoutGroupLimitCheck=False):
        from .factor_converter import FactorConverter
        fc = FactorConverter()

        occupationToAdd = fc.occupation(quantityToAdd, mountedSpace.Space.Size, item, self._check_calculate_additional_occupation(context))
        self._write_log_additional_occupation(context, item, quantityToAdd)

        occupationRemaining = fc.GetOccupationRemainingWithVolumeReduction(context, mountedSpace, item)

        if occupationToAdd <= occupationRemaining:
            if not withoutGroupLimitCheck:
                return self.can_add_basic(context, mountedSpace, item)
            return True

        # context.add_execution_log(f"NaoAdd - OCUPACAO MAIOR - Nao foi possivel adicionar o item {item.Code} - {item.Product.Name} ocupacao {occupationToAdd:.2f} no palete {mountedSpace.Space.Side}/{mountedSpace.Space.Number} ocupacao {occupationRemaining:.2f}")
        return False

    def CanAddMounted(self, *args, **kwargs):
        return self.can_add_mounted(*args, **kwargs)

    def can_add_basic(self, context, mountedSpace, item):
        limitGroups = context.get_setting('ShouldLimitPackageGroups')
        if not limitGroups:
            return True

        canBeAssociated = context.CanBeAssociate(mountedSpace, item)
        if not canBeAssociated:
            # context.add_execution_log(f"NaoAdd - GRUPO SEM ASSOCIACAO - Nao foi possivel adicionar o item {item.Code} - {item.Product.Name} GroupCode {item.Product.PackingGroup.GroupCode} no palete {mountedSpace.Space.Side}/{mountedSpace.Space.Number}")
            return False

        if mountedSpace.IsNewGroup(item) and self.reached_group_limit(context, mountedSpace):
            # context.add_execution_log(f"NaoAdd - PALETE MAX GRUPO - Nao foi possivel adicionar o item {item.Code} - {item.Product.Name} no Palete {mountedSpace.Space.Side}/{mountedSpace.Space.Number}")
            return False

        return True

    def CanAddBasic(self, *args, **kwargs):
        return self.can_add_basic(*args, **kwargs)

    # def can_add_mounted_to_mounted(self, context, mountedSpaceToAdd, mountedSpaceToRemoveItems):
    #     items = [
    #         {
    #             'Item': p.Item,
    #             'Quantity': p.Amount,
    #             'Factor': p.Item.Product.GetFactor(mountedSpaceToAdd.Space.Size)
    #         }
    #         for p in mountedSpaceToRemoveItems.GetProducts()
    #     ]

    #     currentProducts = list({tuple(cont.Products) for cont in mountedSpaceToAdd.Containers})
    #     from .factor_converter import FactorConverter
    #     fc = FactorConverter()

    #     totalOfOccupation = sum(fc.occupation(it['Quantity'], it['Factor'], it['Item'].Product.PalletSetting, it['Item'], self._check_calculate_additional_occupation(context)) for it in items)
    #     occupationRemaining = fc.GetOccupationRemainingWithVolumeReduction(context, mountedSpaceToAdd, mountedSpaceToRemoveItems)

    #     if totalOfOccupation > occupationRemaining:
    #         self._write_log(f"NaoMover - OCUPACAO MAIOR - Nao foi possivel mover os Itens de {mountedSpaceToRemoveItems.Space.Side}/{mountedSpaceToRemoveItems.Space.Number} ocupacao {totalOfOccupation:.2f} para {mountedSpaceToAdd.Space.Side}/{mountedSpaceToAdd.Space.Number} ocupacao {occupationRemaining:.2f}")
    #         return False
        
    #     limitGroups = context.get_setting('ShouldLimitPackageGroups')
    #     if limitGroups:
    #         maxGroups = self.get_max_groups(context)
    #         currentGroups = set(g for cont in mountedSpaceToAdd.Containers for g in (p.Product.PackingGroup.GroupCode for p in cont.Products))

    #         if not all(any(itm['Item'].Product.CanBeAssociated(g) for itm in items) for g in currentGroups):
    #             self._write_log(f"NaoMover - GRUPO SEM ASSOCIACAO - Nao foi possivel mover os Itens de {mountedSpaceToRemoveItems.Space.Side}/{mountedSpaceToRemoveItems.Space.Number} para {mountedSpaceToAdd.Space.Side}/{mountedSpaceToAdd.Space.Number}")
    #             return False

    #         packageGroupsToAdd = set(it['Item'].Product.PackingGroup.GroupCode for it in items)
    #         allGroups = list(packageGroupsToAdd) + list(currentGroups)
    #         if len(allGroups) > maxGroups:
    #             self._write_log(f"NaoMover - PALETE MAX GRUPO {maxGroups} - Nao foi possivel mover os Itens de {mountedSpaceToRemoveItems.Space.Side}/{mountedSpaceToRemoveItems.Space.Number} para {mountedSpaceToAdd.Space.Side}/{mountedSpaceToAdd.Space.Number}")
    #             return False

    #     return True

    def can_add_mounted_to_mounted(self, context, mountedSpaceToAdd, mountedSpaceToRemoveItems):
        from .factor_converter import FactorConverter
        fc = FactorConverter()

        # target_size: se mountedSpaceToAdd for None, usa o size do mountedSpaceToRemoveItems.Space
        try:
            if mountedSpaceToAdd is not None:
                target_size = getattr(mountedSpaceToAdd.Space, 'Size', None)
            else:
                target_size = getattr(mountedSpaceToRemoveItems.Space, 'Size', None)
        except Exception:
            target_size = None

        items = [
            {
                'Item': p.Item,
                'Quantity': p.Amount,
                'Factor': p.Item.Product.GetFactor(target_size)
            }
            for p in mountedSpaceToRemoveItems.GetProducts()
        ]

        # produtos atuais no destino (vazio se mountedSpaceToAdd for None)
        try:
            currentProducts = list({tuple(cont.Products) for cont in mountedSpaceToAdd.Containers}) if mountedSpaceToAdd is not None else []
        except Exception:
            currentProducts = []

        totalOfOccupation = sum(
            fc.occupation(it['Quantity'], it['Factor'], it['Item'].Product.PalletSetting, it['Item'],
                          self._check_calculate_additional_occupation(context))
            for it in items
        )

        # se destino for None, occupationRemaining é o tamanho total do espaço destino
        if mountedSpaceToAdd is None:
            try:
                occupationRemaining = float(target_size)
            except Exception:
                occupationRemaining = 0.0
        else:
            occupationRemaining = fc.GetOccupationRemainingWithVolumeReduction(context, mountedSpaceToAdd, mountedSpaceToRemoveItems)

        if totalOfOccupation > occupationRemaining:
            self._write_log(f"NaoMover - OCUPACAO MAIOR - Nao foi possivel mover os Itens de {mountedSpaceToRemoveItems.Space.Side}/{mountedSpaceToRemoveItems.Space.Number} ocupacao {totalOfOccupation:.2f} para {(mountedSpaceToAdd.Space.Side+'/'+str(mountedSpaceToAdd.Space.Number)) if mountedSpaceToAdd is not None else 'DESTINO_VAZIO'} ocupacao {occupationRemaining:.2f}")
            return False

        limitGroups = context.get_setting('ShouldLimitPackageGroups')
        if limitGroups:
            maxGroups = self.get_max_groups(context)
            currentGroups = set(g for cont in (mountedSpaceToAdd.Containers if mountedSpaceToAdd is not None else []) for g in (p.Product.PackingGroup.GroupCode for p in cont.Products))

            if not all(all(itm['Item'].Product.CanBeAssociated(g) for itm in items) for g in currentGroups):
                self._write_log(f"NaoMover - GRUPO SEM ASSOCIACAO - Nao foi possivel mover os Itens de {mountedSpaceToRemoveItems.Space.Side}/{mountedSpaceToRemoveItems.Space.Number} para {(mountedSpaceToAdd.Space.Side+'/'+str(mountedSpaceToAdd.Space.Number)) if mountedSpaceToAdd is not None else 'DESTINO_VAZIO'}")
                return False

            packageGroupsToAdd = set(it['Item'].Product.PackingGroup.GroupCode for it in items)
            allGroups = list(packageGroupsToAdd) + list(currentGroups)
            if len(allGroups) > maxGroups:
                self._write_log(f"NaoMover - PALETE MAX GRUPO {maxGroups} - Nao foi possivel mover os Itens de {mountedSpaceToRemoveItems.Space.Side}/{mountedSpaceToRemoveItems.Space.Number} para {(mountedSpaceToAdd.Space.Side+'/'+str(mountedSpaceToAdd.Space.Number)) if mountedSpaceToAdd is not None else 'DESTINO_VAZIO'}")
                return False

        return True

    def CanAddMountedToMounted(self, *args, **kwargs):
        return self.can_add_mounted_to_mounted(*args, **kwargs)

    def get_max_groups(self, context):
        if self._max_groups is not None:
            return self._max_groups
        return context.get_setting('MaxPackageGroups')

    def GetMaxGroups(self, context):
        return self.get_max_groups(context)

    def reached_group_limit(self, context, mountedSpace):
        if mountedSpace is None:
            return False
        maxGroups = self.get_max_groups(context)
        currentGroups = set(p.Product.PackingGroup.GroupCode for c in mountedSpace.Containers for p in c.Products)
        return len(currentGroups) >= maxGroups

    def ReachedGroupLimit(self, *args, **kwargs):
        return self.reached_group_limit(*args, **kwargs)

    def _check_calculate_additional_occupation(self, context):
        if not context.get_setting('OccupationAdjustmentToPreventExcessHeight'):
            # self._write_log("Configuração OccupationAdjustmentToPreventExcessHeight desativada, regra não será executada")
            return False
        return True

    def _write_log(self, message, addInsideContext=None, ruleName=None):
        print(message)
        if addInsideContext is None:
            return
        # addInsideContext.Execution.Current.AddLog(f"{ruleName or 'DomainOperations'} - {message}")

    def _write_log_additional_occupation(self, context, item, quantityToAdd):
        if item.AdditionalOccupation > 0:
            self._write_log(f"Definindo 'Ocupação extra:' {item.AdditionalOccupation:.2f} ao Item: {item.Code} com quantidade: {quantityToAdd}", context, f"{context.get_setting('OccupationAdjustmentToPreventExcessHeight')}Rule")

    def WriteLog(self, *args, **kwargs):
        return self._write_log(*args, **kwargs)

    def WriteLogAdditionalOccupation(self, *args, **kwargs):
        return self._write_log_additional_occupation(*args, **kwargs)

    # def join_grouped_spaces(self, context, items, grouped_spaces):
    #     """Attempt to join grouped mounted spaces by moving/adding items.

    #     Minimal behavior: iterate groups and try to add remaining items to
    #     each space in the group until items are exhausted.
    #     """
    #     for group in grouped_spaces:
    #         for ms in group:
    #             space = getattr(ms, 'space', ms)
    #             for item in list(items):
    #                 if getattr(item, 'amount_remaining', 0) <= 0:
    #                     continue
    #                 qty = min(item.amount_remaining, int(getattr(space, 'size', 0) or 0))
    #                 if qty <= 0:
    #                     continue
    #                 context.add_product(space, item, qty)

    def join_grouped_spaces(self, context, items, grouped_spaces):
        """Faithful port of C# JoinGroupedSpaces.
        
        Uses GroupBy pattern to group items by PackingGroup.GroupCode,
        checks if any group code doesn't have a mounted space (using
        HasSpaceAndNotBlocked and WithGroupCodeAndNotChopp filters),
        and if so delegates to JoinSpaces.
        """
        from itertools import groupby
        
        if not grouped_spaces:
            return

        # Helper: HasSpaceAndNotBlocked - matches C# extension method
        def has_space_and_not_blocked(ms):
            # C#: !mountedSpace.Full && !mountedSpace.Blocked
            full = getattr(ms, "Full", False)
            blocked = getattr(ms, "Blocked", False)
            return not full and not blocked

        # Helper: WithGroupCode - matches C# ContainerExtensions.WithGroupCode
        def with_group_code(containers, group_code):
            # C#: containers.Any(x => x.ProductBase.PackingGroup.GroupCode == groupCode)
            for container in containers:
                product_base = getattr(container, "ProductBase", None)
                if product_base:
                    packing_group = getattr(product_base, "PackingGroup", None)
                    if packing_group and getattr(packing_group, "GroupCode", None) == group_code:
                        return True
            return False

        # Helper: IsTypeBaseChopp - matches C# ContainerExtensions.IsTypeBaseChopp
        def is_type_base_chopp(containers):
            # C#: containers.Any(y => y.IsTypeBaseChopp())
            for container in containers:
                if hasattr(container, "IsTypeBaseChopp"):
                    if callable(container.IsTypeBaseChopp):
                        if container.IsTypeBaseChopp():
                            return True
                    elif container.IsTypeBaseChopp:
                        return True
            return False

        # Helper: WithGroupCodeAndNotChopp - matches C# MountedSpaceExtensions
        def with_group_code_and_not_chopp(spaces, group_code):
            # C#: spaces.Any(p => p.Containers.WithGroupCode(groupCode) && !p.Containers.IsTypeBaseChopp())
            for ms in spaces:
                containers = getattr(ms, "Containers", [])
                if with_group_code(containers, group_code) and not is_type_base_chopp(containers):
                    return True
            return False

        # C# GroupBy pattern: items.GroupBy(p => p.Product.PackingGroup.GroupCode).Select(p => p.Key)
        sorted_items = sorted(items, key=lambda it: getattr(getattr(it.Product, "PackingGroup", None), "GroupCode", 0))
        group_codes = [k for k, _ in groupby(sorted_items, key=lambda it: getattr(getattr(it.Product, "PackingGroup", None), "GroupCode", 0))]

        # Flatten grouped_spaces: groupedSpaces.SelectMany(d => d)
        flattened = [ms for grp in grouped_spaces for ms in grp]

        # Filter to HasSpaceAndNotBlocked
        filtered_spaces = [ms for ms in flattened if has_space_and_not_blocked(ms)]

        # Find groups without mounted spaces
        # C#: .Where(groupCode => !groupedSpaces.SelectMany(d => d).HasSpaceAndNotBlocked().WithGroupCodeAndNotChopp(groupCode))
        groups_without_mounted_spaces = [
            code for code in group_codes
            if not with_group_code_and_not_chopp(filtered_spaces, code)
        ]

        if not groups_without_mounted_spaces:
            return

        # Delegate to JoinSpaces
        self.join_spaces(context, grouped_spaces)

    def join_spaces(self, context, grouped_spaces):
        """
        Port of C# JoinSpaces:
        - for each group order mounted spaces by Occupation (asc)
        - walk pairs (space1, space2) and call change_product which must return
          (space1, space2, changed) to emulate C# ref semantics
        """
        if not grouped_spaces:
            return

        for group in grouped_spaces:
            # order by occupation ascending
            try:
                ordered = sorted(group, key=lambda p: getattr(p, "Occupation", getattr(p, "occupation", 0)))
            except Exception:
                ordered = list(group)

            space1 = None
            space2 = None

            for sp in ordered:
                if space1 is None:
                    space1 = sp
                else:
                    space2 = sp

                # change_product must return (space1, space2, changed)
                try:
                    space1, space2, changed = self.change_product(context, space1, space2)
                except Exception as e:
                    print("Error in change_product:", e)
                    # fall back to calling a boolean-returning change_product if implemented differently
                    changed = False
                    try:
                        changed = self.change_product(context, space1, space2)  # if returns bool
                    except Exception:
                        changed = False

                if changed:
                    break

    def sum_of_occupations_is_smaller_then_space_size(self, space_size: int, occupation1: float, occupation2: float) -> bool:
        return occupation1 + occupation2 <= space_size

    def get_mounted_products_with_occupation(self, base_space, space1, space2, calculate_additional_occupation):
        results = []
        for container in base_space.Containers:
            for mp in container.Products:
                occ1 = FactorConverter().occupation(mp.Amount, mp.Product.GetFactor(space1.Space.Size), mp.Product.PalletSetting, mp.Item, calculate_additional_occupation)
                occ2 = FactorConverter().occupation(mp.Amount, mp.Product.GetFactor(space2.Space.Size), mp.Product.PalletSetting, mp.Item, calculate_additional_occupation)
                results.append({
                    "mounted_product": mp,
                    "occupation_space1": occ1,
                    "occupation_space2": occ2
                })
        return results

    def change_product(self, context, space1, space2):
        """
        Port of ChangeProduct C# logic.
        Returns tuple (space1, space2, changed) where space1/space2 may be set to None
        to emulate the ref/null logic from C# and changed is a boolean indicating a swap.
        """
        if space1 is None or space2 is None:
            return (space1, space2, False)

        mounted_products_space1 = self.get_mounted_products_with_occupation(space1, space1, space2, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))
        mounted_products_space2 = self.get_mounted_products_with_occupation(space2, space1, space2, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))

        occupation_space1_in_space1 = sum(p["occupation_space1"] for p in mounted_products_space1)
        occupation_space2_in_space2 = sum(p["occupation_space1"] for p in mounted_products_space2)

        occupation_space2_in_space1 = sum(p["occupation_space2"] for p in mounted_products_space1)
        occupation_space1_in_space2 = sum(p["occupation_space2"] for p in mounted_products_space2)

        percentage_occupation_space1 = occupation_space1_in_space1 * 100 / int(space1.Space.Size)
        percentage_occupation_space2 = occupation_space1_in_space2 * 100 / int(space2.Space.Size)

        space_size1 = int(space1.Space.Size)
        space_size2 = int(space2.Space.Size)

        # follow the same branch order as C#
        if self.sum_of_occupations_is_smaller_then_space_size(space_size1, occupation_space1_in_space1, occupation_space2_in_space2) and percentage_occupation_space1 < percentage_occupation_space2:
            changed = self.change_product_full_space(context, space1, space2)
            return (space1, space2, changed)
        elif self.sum_of_occupations_is_smaller_then_space_size(space_size2, occupation_space2_in_space1, occupation_space1_in_space2) and percentage_occupation_space2 < percentage_occupation_space1:
            changed = self.change_product_full_space(context, space2, space1)
            return (space1, space2, changed)
        elif self.sum_of_occupations_is_smaller_then_space_size(space_size1, occupation_space1_in_space1, occupation_space2_in_space2):
            changed = self.change_product_full_space(context, space1, space2)
            return (space1, space2, changed)
        elif self.sum_of_occupations_is_smaller_then_space_size(space_size2, occupation_space2_in_space1, occupation_space1_in_space2):
            changed = self.change_product_full_space(context, space2, space1)
            return (space1, space2, changed)
        else:
            if percentage_occupation_space1 > occupation_space2_in_space2:
                space1 = None
            else:
                space2 = None
            return (space1, space2, False)

    def AddOnBestSpace(self, *args, **kwargs):
        return self.add_on_best_space(*args, **kwargs)    
       
    # def add_on_best_space(self, context, best_spaces, item):
    #     """Add item on the best mounted spaces sequence until depleted."""
    #     for ms in best_spaces:
    #         if getattr(item, 'amount_remaining', 0) <= 0:
    #             break
    #         space = getattr(ms, 'space', ms)
    #         qty = min(item.amount_remaining, int(getattr(space, 'size', 0) or 0))
    #         if qty <= 0:
    #             continue
    #         context.add_product(space, item, qty)

    def add_on_best_space(self, context, best_spaces, item):
        """Faithful port of C# AddOnBestSpace:

        - If item has no remaining amount, return
        - If provided spaces contains 1 or 0 entries, return
        - Otherwise take the first two mounted-spaces, extract their `.Space` and
          call AddOn2Spaces(context, space1, space2, item)
        """

        if not item.HasAmountRemaining():
            return

        try:
            array_spaces = list(best_spaces)
        except Exception:
            return

        if len(array_spaces) <= 1:
            return

        # extract ISpace-like objects from the first two mounted spaces
        try:
            ms0 = array_spaces[0]
            ms1 = array_spaces[1]
            space1 = getattr(ms0, 'Space', getattr(ms0, 'space', None))
            space2 = getattr(ms1, 'Space', getattr(ms1, 'space', None))
        except Exception:
            return

        if space1 is not None and space2 is not None:
            try:
                self.AddOn2Spaces(context, space1, space2, item)
            except Exception:
                return

    def add_on_2_spaces(self, context, space1, space2, item):
        """Faithful port of C# MountedSpaceOperations.AddOn2Spaces.

        Steps:
        - compute how many units fit in priority and secondary spaces
        - if combined capacity >= item.AmountRemaining, try to split across them
        - call helper add_splitted_product_on_space for each side as needed
        """
        # quick check for remaining amount
        try:
            has_remaining = item.HasAmountRemaining() if hasattr(item, 'HasAmountRemaining') else (getattr(item, 'AmountRemaining', getattr(item, 'amount_remaining', 0)) > 0)
        except Exception:
            has_remaining = getattr(item, 'AmountRemaining', getattr(item, 'amount_remaining', 0)) > 0
        if not has_remaining:
            return

        from .factor_converter import FactorConverter
        fc = FactorConverter()

        try:
            mounted_priority = context.GetMountedSpace(space1)
        except Exception:
            mounted_priority = context.get_mounted_space(space1) if hasattr(context, 'get_mounted_space') else None

        try:
            mounted_secondary = context.GetMountedSpace(space2)
        except Exception:
            mounted_secondary = context.get_mounted_space(space2) if hasattr(context, 'get_mounted_space') else None

        try:
            priority_qty = int(fc.QuantityToRemainingSpace(mounted_priority, item, getattr(context, 'Settings', getattr(context, 'settings', None))))
        except Exception as e:
            print("Error computing priority_qty:", e)
            try:
                priority_qty = int(fc.QuantityToRemainingSpace(mounted_priority, item, context))
            except Exception as e:
                print("Error computing priority_qty:", e)
                priority_qty = 0

        try:
            secondary_qty = int(fc.QuantityToRemainingSpace(mounted_secondary, item, getattr(context, 'Settings', getattr(context, 'settings', None))))
        except Exception as e:
            print("Error computing secondary_qty:", e)
            try:
                secondary_qty = int(fc.QuantityToRemainingSpace(mounted_secondary, item, context))
            except Exception as e:
                print("Error computing secondary_qty:", e)
                secondary_qty = 0

        try:
            amount_remaining = getattr(item, 'AmountRemaining', getattr(item, 'amount_remaining', 0))
        except Exception:
            amount_remaining = 0

        if (priority_qty + secondary_qty) >= int(amount_remaining):
            if priority_qty > 0:
                try:
                    self.add_splitted_product_on_space(context, space1, item)
                except Exception:
                    try:
                        # PascalCase alias if used elsewhere
                        self.AddSplittedProductOnSpace(context, space1, item)
                    except Exception:
                        pass

            if secondary_qty > 0 and (getattr(item, 'AmountRemaining', getattr(item, 'amount_remaining', 0)) > 0):
                try:
                    self.add_splitted_product_on_space(context, space2, item)
                except Exception:
                    try:
                        self.AddSplittedProductOnSpace(context, space2, item)
                    except Exception:
                        pass
        return True

    # PascalCase alias
    AddOn2Spaces = add_on_2_spaces

    def add_splitted_product_on_space(self, context, space, item):
        """Faithful port of C# MountedSpaceOperations.AddSplittedProductOnSpace.

        Calculates how many units fit into the mounted space, validates can-add,
        splits the item, and adds the computed quantity to the space.
        """
        from .factor_converter import FactorConverter
        import math

        fc = FactorConverter()

        # resolve factor and mounted space
        try:
            prod = getattr(item, 'Product', getattr(item, 'product', None))
            space_size = getattr(space, 'Size', getattr(space, 'size', None))
            factor = getattr(prod, 'GetFactor', getattr(prod, 'get_factor'))(space_size) if prod is not None else None
        except Exception:
            factor = None

        try:
            mounted_space = context.GetMountedSpace(space)
        except Exception:
            mounted_space = context.get_mounted_space(space) if hasattr(context, 'get_mounted_space') else None

        try:
            occ_remaining = getattr(mounted_space, 'OccupationRemaining', getattr(mounted_space, 'occupation_remaining', getattr(mounted_space, 'occupation', 0)))
        except Exception:
            occ_remaining = getattr(mounted_space, 'occupation_remaining', getattr(mounted_space, 'occupation', 0))

        try:
            calculate_additional = context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
        except Exception:
            calculate_additional = getattr(getattr(context, 'Settings', getattr(context, 'settings', {})), 'OccupationAdjustmentToPreventExcessHeight', False)

        try:
            qty_decimal = fc.QuantityPerFactor(occ_remaining, getattr(item, 'AmountRemaining', getattr(item, 'amount_remaining', 0)), factor, item, calculate_additional)
            # quantity_to_remaining_space = int(math.floor(float(qty_decimal)))#temporario 17_12_2025
            quantity_to_remaining_space = int(qty_decimal // 1)
        except Exception:
            quantity_to_remaining_space = 0

        try:
            if int(getattr(item, 'AmountRemaining', getattr(item, 'amount_remaining', 0))) < int(quantity_to_remaining_space):
                return
        except Exception:
            pass

        # check domain can add (uses DomainOperations.can_add / CanAdd)
        try:
            can_add = self.can_add(context, space, item, quantity_to_remaining_space)
        except Exception:
            try:
                can_add = self.CanAdd(context, space, item, quantity_to_remaining_space)
            except Exception:
                can_add = True

        if not can_add:
            return

        # split and add
        try:
            if hasattr(item, 'Split') and callable(getattr(item, 'Split')):
                item.Split()
            elif hasattr(item, 'split') and callable(getattr(item, 'split')):
                item.split()
        except Exception:
            pass

        try:
            first_layer = mounted_space.GetNextLayer() if hasattr(mounted_space, 'GetNextLayer') else (mounted_space.get_next_layer() if hasattr(mounted_space, 'get_next_layer') else 0)
        except Exception:
            first_layer = 0

        try:
            occupation = fc.Occupation(quantity_to_remaining_space, getattr(space, 'Size', getattr(space, 'size', None)), item, calculate_additional)
        except Exception:
            try:
                occupation = fc.Occupation(quantity_to_remaining_space, getattr(space, 'size', getattr(space, 'Size', None)), item, calculate_additional)
            except Exception:
                occupation = 0

        try:
            quantity_of_layer = 0
            prod = getattr(item, 'Product', getattr(item, 'product', None))
            if prod is not None:
                if hasattr(prod, 'GetQuantityOfLayerToSpace'):
                    quantity_of_layer = prod.GetQuantityOfLayerToSpace(getattr(space, 'Size', getattr(space, 'size', None)), quantity_to_remaining_space)
                elif hasattr(prod, 'get_quantity_of_layer_to_space'):
                    quantity_of_layer = prod.get_quantity_of_layer_to_space(getattr(space, 'size', getattr(space, 'Size', None)), quantity_to_remaining_space)
        except Exception:
            quantity_of_layer = 0

        try:
            # if hasattr(context, 'add_product'):
            context.AddProduct(space, item, quantity_to_remaining_space, first_layer, quantity_of_layer, occupation)
            # else:
            #     context.AddProduct(space, item, quantity_to_remaining_space, first_layer, quantity_of_layer, occupation)
        except Exception as e:
            print("Error adding product with layers:", e)
            try:
                # fallback without layers
                if hasattr(context, 'add_product'):
                    context.add_product(space, item, quantity_to_remaining_space)
                else:
                    context.AddProduct(space, item, quantity_to_remaining_space)
            except Exception as e:
                print("Error adding product without layers:", e)
                pass

        # log
        try:
            side = getattr(space, 'sideDesc', getattr(space, 'side', '?'))
            number = getattr(space, 'Number', getattr(space, 'number', '?'))
            occ_val = getattr(mounted_space, 'Occupation', getattr(mounted_space, 'occupation', None))
            # self._write_log(f"Item {getattr(item, 'Code', getattr(item, 'code', '?'))} quebrado adicionado no espaco {number} / {side}, nova ocupacao de {occ_val}", context)
            context.add_execution_log(f"Item {getattr(item, 'Code', getattr(item, 'code', '?'))} quebrado adicionado no espaco {number} / {side}, nova ocupacao de {occ_val}")
        except Exception:
            pass

    # PascalCase alias
    AddSplittedProductOnSpace = add_splitted_product_on_space

    # @dispatch(object, Space, MountedSpace, MountedProduct)
    # def move_mounted_product(self, context: object, target_space: Space, source_mounted_space: MountedSpace, source_mounted_product: MountedProduct):
    #     # signature used by some callers: include source mounted-space
    #     return self.move_mounted_product(context, target_space, source_mounted_product)

    # @dispatch(object, Space, MountedSpace, MountedProduct, int)
    # def move_mounted_product(self, context: object, target_space: Space, source_mounted_space: MountedSpace, source_mounted_product: MountedProduct, quantity_to_move: int):
        # signature used by some callers: include source mounted-space and quantity
        # return self.move_mounted_product(context, target_space, source_mounted_product, quantity_to_move)

    @dispatch(object, Space, MountedProduct)
    def move_mounted_product(self, context: Any, target_space: Space, source_mounted_product: MountedProduct):
        # delegate to overload that accepts quantity using the mounted product current amount
        quantity = getattr(source_mounted_product, 'amount', None)
        if quantity is None: 
            quantity = getattr(source_mounted_product, 'Amount', None)
        if quantity is None:
            quantity = 0
        return self.move_mounted_product(context, target_space, source_mounted_product, int(quantity))

    @dispatch(object, Space, MountedSpace, MountedProduct)
    def move_mounted_product(self, context: Any, target_space: Space, source_mounted_space: MountedSpace, source_mounted_product: MountedProduct):
        # signature used by some callers: include source mounted-space
        return self.move_mounted_product(context, target_space, source_mounted_space ,source_mounted_product, source_mounted_product.Amount) 

    @dispatch(object, Space, MountedSpace, MountedProduct, int)
    def move_mounted_product(self, context: Any, target_space: Space, source_mounted_space: MountedSpace, source_mounted_product: MountedProduct, quantity_to_move: int):
        # Faithful port of the C# MoveMountedProduct(context, ISpace, IMountedSpace, IMountedProduct, int)

        try:#temp
            origin_space = getattr(getattr(source_mounted_space, 'space', None), 'number', None) or getattr(getattr(source_mounted_space, 'Space', None), 'Number', None)
            origin_side = getattr(getattr(source_mounted_space, 'space', None), 'side', None) or getattr(getattr(source_mounted_space, 'Space', None), 'Side', None)
        except Exception:
            origin_space = origin_side = None
        try:
            target_num = getattr(target_space, 'number', None) or getattr(target_space, 'Number', None) or getattr(target_space, 'Id', None)
            target_side = getattr(target_space, 'side', None) or getattr(target_space, 'Side', None) or getattr(target_space, 'Name', None)
        except Exception:
            target_num = target_side = None

        self._write_log(f"DEBUG MoveMountedProduct - origem: {origin_space} / {origin_side}  destino: {target_num} / {target_side}", context)
        #temp

        try:
            product_name = getattr(getattr(source_mounted_product, 'product', None), 'name', getattr(getattr(source_mounted_product, 'Product', None), 'Name', None))
        except Exception:
            product_name = None

        from .factor_converter import FactorConverter
        fc = FactorConverter()

        try:
            occupation_to_add = fc.occupation(quantity_to_move, source_mounted_product.product.get_factor(getattr(target_space, 'size', getattr(target_space, 'Size', None))) if getattr(source_mounted_product, 'product', None) is not None else None, getattr(source_mounted_product, 'product', getattr(source_mounted_product, 'Product', None)).PalletSetting if getattr(getattr(source_mounted_product, 'product', getattr(source_mounted_product, 'Product', None)), 'PalletSetting', None) is not None else None, getattr(source_mounted_product, 'item', getattr(source_mounted_product, 'Item', None)), self._check_calculate_additional_occupation(context)) 
        except Exception:
            return False

        try:
            target_size = getattr(target_space, 'size', getattr(target_space, 'Size', None))
            if target_size is not None and (float(target_size) < float(occupation_to_add)):
                return False
        except Exception:
            pass

        try:
            if not self.can_add_space(context, target_space, getattr(source_mounted_product, 'item', getattr(source_mounted_product, 'Item', None)), quantity_to_move, move=True):
                return False
        except Exception:
            return False

        try:
            # container = source_mounted_space.GetFirstPallet()
            container = None
            if hasattr(source_mounted_space, 'get_first_pallet'):
                container = source_mounted_space.get_first_pallet()
            elif hasattr(source_mounted_space, 'GetFirstPallet'):
                container = source_mounted_space.GetFirstPallet()
        except Exception as e:
            print(f"Error getting container: {e}")
            container = None

        try:
            first_layer = source_mounted_space.GetNextLayer() if hasattr(source_mounted_space, 'GetNextLayer') else (source_mounted_space.get_next_layer() if hasattr(source_mounted_space, 'get_next_layer') else 0)
        except Exception as e:
            print(f"Error getting first layer: {e}")
            first_layer = 0

        try:
            quantity_of_layer = 0
            if getattr(source_mounted_product, 'product', None) is not None and hasattr(source_mounted_product.product, 'get_quantity_of_layer_to_space'):
                quantity_of_layer = source_mounted_product.product.get_quantity_of_layer_to_space(getattr(target_space, 'size', getattr(target_space, 'Size', None)), quantity_to_move)
            elif getattr(source_mounted_product, 'Product', None) is not None and hasattr(source_mounted_product.Product, 'GetQuantityOfLayerToSpace'):
                quantity_of_layer = source_mounted_product.Product.GetQuantityOfLayerToSpace(getattr(target_space, 'size', getattr(target_space, 'Size', None)), quantity_to_move)
        except Exception as e:
            print(f"Error getting quantity of layer: {e}")
            quantity_of_layer = 0

        try:
            # Add product from mounted product into target
            if hasattr(context, 'add_product_from_mounted_product'):
                context.add_product_from_mounted_product(target_space, source_mounted_product, quantity_to_move, first_layer, quantity_of_layer, occupation_to_add)
            else:
                context.AddProductFromMountedProduct(target_space, source_mounted_product, quantity_to_move, first_layer, quantity_of_layer, occupation_to_add)
        except Exception as e:
            print(f"Error adding product from mounted product: {e}")
            return False

        try:
            # use signature occupation(quantity:int, space_size:Decimal, item:Item, calculate_additional:bool)
            space_size_src = None
            try:
                space_size_src = getattr(getattr(source_mounted_space, 'Space', getattr(source_mounted_space, 'space', None)), 'Size', getattr(getattr(source_mounted_space, 'Space', getattr(source_mounted_space, 'space', None)), 'size', None))
            except Exception:
                space_size_src = getattr(getattr(source_mounted_space, 'space', None), 'size', None)

            item_src = getattr(source_mounted_product, 'item', getattr(source_mounted_product, 'Item', None))

            occupation_to_remove = fc.occupation(quantity_to_move, space_size_src, item_src, self._check_calculate_additional_occupation(context))
            if hasattr(source_mounted_space, 'decrease_occupation'):
                source_mounted_space.decrease_occupation(occupation_to_remove)
            elif hasattr(source_mounted_space, 'DecreaseOccupation'):
                source_mounted_space.DecreaseOccupation(occupation_to_remove)
            else:
                try:
                    cur = float(getattr(source_mounted_space, 'occupation', 0) or 0)
                    source_mounted_space.occupation = cur - float(occupation_to_remove)
                except Exception:
                    pass
        except Exception as e:
            print(f"Error decreasing occupation: {e}")
            pass

        try:
            if getattr(source_mounted_product, 'amount', getattr(source_mounted_product, 'Amount', None)) == 0 and container is not None:
                if hasattr(container, 'remove_mounted_product'):
                    container.remove_mounted_product(source_mounted_product)
                elif hasattr(container, 'RemoveMountedProduct'):
                    container.RemoveMountedProduct(source_mounted_product)
        except Exception as e:
            print(f"Error removing mounted product from container: {e}")
            pass

        try:
            products = None
            if container is not None:
                if hasattr(container, 'get_products'):
                    products = container.get_products()
                elif hasattr(container, 'Products'):
                    products = container.Products
                elif hasattr(container, 'products'):
                    products = container.products

            if not products:
                if hasattr(source_mounted_space, 'clear'):
                    source_mounted_space.clear()
                elif hasattr(source_mounted_space, 'Clear'):
                    source_mounted_space.Clear()
        except Exception as e:
            print(f"Error clearing source mounted space: {e}")
            pass

        try:
            # build detailed log: product, qty, origin pallet (number/side) -> target space (number/side) and occupation
            try:
                origin_space = getattr(source_mounted_space, 'Space', getattr(source_mounted_space, 'space', None))
            except Exception:
                origin_space = None
            try:
                origin_number = getattr(origin_space, 'Number', getattr(origin_space, 'number', '?'))
            except Exception:
                origin_number = '?'
            try:
                origin_side = origin_space.sideDesc #getattr(origin_space, 'Side', getattr(origin_space, 'side', '?'))
            except Exception:
                origin_side = '?'

            try:
                dest_number = getattr(target_space, 'Number', getattr(target_space, 'number', '?'))
            except Exception:
                dest_number = '?'
            try:
                dest_side = target_space.sideDesc #getattr(target_space, 'Side', getattr(target_space, 'side', '?'))
            except Exception:
                dest_side = '?'

            try:
                occ_str = f"{float(occupation_to_add):.2f}".replace('.', ',')
            except Exception:
                try:
                    occ_str = str(occupation_to_add)
                except Exception:
                    occ_str = '?'

            prod_display = product_name

            msg = f"Distribuído o produto {prod_display} na quantidade {quantity_to_move} do palete de origem {origin_number} / {origin_side}, para o espaço {dest_number} / {dest_side} com a ocupação {occ_str}"
            context.add_execution_log(msg)
        except Exception as e:
            print(f"Error writing detailed log: {e}")
            pass

        return True

    @dispatch(object, Space, MountedProduct, int)
    def move_mounted_product(self, context: Any, target_space: Space, source_mounted_product: MountedProduct, quantity_to_move: int):
        # fallback: obtain source mounted-space from the mounted product and delegate
        source_mounted_space = getattr(source_mounted_product, 'mounted_space', getattr(source_mounted_product, 'MountedSpace', None))
        return self.move_mounted_product(context, target_space, source_mounted_space, source_mounted_product, quantity_to_move)

    def move_mounted_products(self, context, empty_space, remount_mounted_space, disposable_mounted_products):
        """Move multiple mounted products from a remount mounted-space into an empty space (or mounted-space).

        Simple behavior: iterate the provided mounted products and move each to the empty_space (or target mounted-space)
        using move_mounted_product. Returns the count of moved products.
        """
        moved = 0
        for mp in list(disposable_mounted_products):
            ok = self.move_mounted_product(context, empty_space, remount_mounted_space, mp)
            if ok:
                moved += 1
        return moved

    def add_amount_remaining_item_into_mounted_space(self, context, item, mounted_space):
        """
        Port of C# AddAmountRemainingItemIntoMountedSpace
        """
        if not self.CanAdd(context, mounted_space, item, item.AmountRemaining):
            return

        first_layer = mounted_space.GetNextLayer()
        quantity_of_layer = item.Product.GetQuantityOfLayerToSpace(mounted_space.Space.Size, item.AmountRemaining)
        occupation = FactorConverter().occupation(item.AmountRemaining, mounted_space.Space.Size, item, context.get_setting('OccupationAdjustmentToPreventExcessHeight'))
        context.AddProduct(mounted_space.Space, item, item.AmountRemaining, first_layer, quantity_of_layer, occupation)


    # def add_amount_remaining_item_into_mounted_space(self, context, item, mounted_space):
    #     """Add the remaining amount of an item into the provided mounted_space.

    #     Behavior:
    #     - Repeatedly call context.add_product on the mounted_space.space using the remaining amount until
    #       the item's amount_remaining is zero or no progress is made.
    #     - This implementation assumes mounted_space has a .space with a numeric .size and item.amount_remaining exists.
    #     """
    #     try:
    #         while item.amount_remaining > 0:
    #             space = mounted_space.space
    #             capacity = int(space.size)
    #             qty = min(int(item.amount_remaining), capacity)
    #             if qty <= 0:
    #                 break
    #             context.add_product(space, item, qty)
    #         return True
    #     except Exception:
    #         return False

    def ordered_by_size_and_number(self, spaces):
        if spaces is None:
            return []

        try:
            lst = list(spaces)
        except Exception:
            return []

        try:
            return sorted(lst, key=lambda x: (x.size, x.number))
        except Exception as e:
            print(f"Error ordering spaces: {e}")
            return lst

    def ordered_by(self, items, fields):
        """
        Ordena dinamicamente uma lista de objetos ou dicionários por múltiplos campos.

        Parâmetros:
            items (iterable): lista de objetos ou dicionários
            fields (list[tuple] | list[str]): lista de campos ou (campo, ordem)
                - campo: nome do atributo/chave
                - ordem: "asc" (padrão) ou "desc"

        Exemplo:
            self.ordered_by(spaces, ["size", "number"])
            self.ordered_by(spaces, [("size", "asc"), ("number", "desc")])
        """

        if not items:
            return []

        try:
            lst = list(items)
        except Exception:
            return []

        def get_value(x, field):
            if isinstance(x, dict):
                v = x.get(field)
            else:
                v = getattr(x, field, None)
            # None cannot be compared in Python sort; treat as 0
            return v if v is not None else 0

        # Normaliza os campos para tuplas (campo, ordem)
        normalized_fields = []
        for f in fields:
            if isinstance(f, tuple):
                field, order = f
            else:
                field, order = f, "asc"
            normalized_fields.append((field, order.lower()))

        # Ordena de trás pra frente para manter prioridade correta
        for field, order in reversed(normalized_fields):
            reverse = order == "desc"
            lst.sort(key=lambda x: get_value(x, field), reverse=reverse)

        return lst

    def change_product_full_space(self, context, mounted_space_to_add, mounted_space_to_remove):
        """Faithful port of C# ChangeProductFullSpace.
        
        Moves all products from mountedSpaceToRemove into mountedSpaceToAdd if they fit.
        Uses Containers.SelectMany(x => x.Products) pattern to get all mounted products.
        """
        fc = FactorConverter()

        space_size_to_add = mounted_space_to_add.Space.Size
        
        # C#: mountedSpaceToRemove.Containers.SelectMany(x => x.Products)
        products_from_remove = []
        for container in mounted_space_to_remove.Containers:
            products_from_remove.extend(container.Products)
        
        # C#: .Select(x => new { Product = x, Occupation = ... })
        quantity_products_on_pallet_to_remove = []
        for x in products_from_remove:
            occ = fc.Occupation(
                x.Amount,
                x.Product.GetFactor(space_size_to_add),
                x.Product.PalletSetting,
                x.Item,
                context.get_setting('OccupationAdjustmentToPreventExcessHeight')
            )
            quantity_products_on_pallet_to_remove.append({
                'Product': x,
                'Occupation': occ
            })

        # C#: if (quantityProductsOnPalletToRemove.Sum(p => p.Occupation) > mountedSpaceToAdd.OccupationRemaining)
        total_occ = sum(p['Occupation'] for p in quantity_products_on_pallet_to_remove)
        if total_occ > mounted_space_to_add.OccupationRemaining:
            return False

        # C#: var allProducts = mountedSpaceToAdd.Containers.SelectMany(x => x.Products).Concat(...)
        all_products = []
        for container in mounted_space_to_add.Containers:
            all_products.extend(container.Products)
        all_products.extend(products_from_remove)

        # C#: var newOccupation = allProducts.Sum(x => _factorConverter.Occupation(...))
        new_occupation = 0
        for x in all_products:
            occ = fc.Occupation(
                x.Amount,
                x.Product.GetFactor(space_size_to_add),
                x.Product.PalletSetting,
                x.Item,
                context.get_setting('OccupationAdjustmentToPreventExcessHeight')
            )
            new_occupation += occ

        # C#: var canAddAllProducts = _contextActions.CanAdd(context, mountedSpaceToAdd, mountedSpaceToRemove)
        can_add_all_products = self.CanAdd(context, mounted_space_to_add, mounted_space_to_remove)
        if not can_add_all_products:
            return False

        # C#: context.SwitchProducts(mountedSpaceToAdd, mountedSpaceToRemove, newOccupation)
        context.SwitchProducts(mounted_space_to_add, mounted_space_to_remove, new_occupation)
        
        context.add_execution_log(
            f"Produtos trocados de {mounted_space_to_remove.Space.Number} / {mounted_space_to_remove.Space.sideDesc} "
            f"para {mounted_space_to_add.Space.Number} / {mounted_space_to_add.Space.sideDesc}, "
            f"nova ocupacao de {mounted_space_to_add.Occupation}"
        )
        
        return True

    @dispatch(object, object)
    def switch_spaces(self, spaceDto1:Any, spaceDto2:Any):
        """SwitchSpaces(SpaceWithMountedSpaceDto, SpaceWithMountedSpaceDto)

        Port of C# behaviour: if MountedSpace present on the dto, set its Space
        to the other DTO.Space. This variant does not use the context and does
        not add/remove spaces.
        """
        auxiliary_space = getattr(spaceDto1, 'Space', None)

        if getattr(spaceDto1, 'MountedSpace', None) is not None:
            try:
                spaceDto1.MountedSpace.SetSpace(spaceDto2.Space)
            except Exception:
                try:
                    spaceDto1.MountedSpace.Space = spaceDto2.Space
                except Exception:
                    setattr(spaceDto1.MountedSpace, 'Space', spaceDto2.Space)

        if getattr(spaceDto2, 'MountedSpace', None) is not None:
            try:
                spaceDto2.MountedSpace.SetSpace(auxiliary_space)
            except Exception:
                try:
                    spaceDto2.MountedSpace.Space = auxiliary_space
                except Exception:
                    setattr(spaceDto2.MountedSpace, 'Space', auxiliary_space)

        return True

    @dispatch(object, object, object)
    def switch_spaces(self, context:object, spaceDto1:object, spaceDto2:object):
        """SwitchSpaces(context, SpaceWithMountedSpaceDto, SpaceWithMountedSpaceDto)

        Port of C# MountedSpaceOperations.SwitchSpaces(context, dto1, dto2):
        if a DTO has a MountedSpace, call SetSpace on it; otherwise use
        context.AddMountedSpaceFromSpace / context.RemoveSpace for empty bays.
        """
        auxiliary_space = getattr(spaceDto1, 'Space', None)

        if getattr(spaceDto1, 'MountedSpace', None) is not None:
            try:
                spaceDto1.MountedSpace.SetSpace(spaceDto2.Space)
            except Exception:
                try:
                    spaceDto1.MountedSpace.Space = spaceDto2.Space
                except Exception:
                    setattr(spaceDto1.MountedSpace, 'Space', spaceDto2.Space)
        else:
            try:
                if hasattr(context, 'AddMountedSpaceFromSpace'):
                    context.AddMountedSpaceFromSpace(spaceDto2.Space)
                if hasattr(context, 'RemoveSpace'):
                    context.RemoveSpace(spaceDto1.Space)
            except Exception:
                pass

        if getattr(spaceDto2, 'MountedSpace', None) is not None:
            try:
                spaceDto2.MountedSpace.SetSpace(auxiliary_space)
            except Exception:
                try:
                    spaceDto2.MountedSpace.Space = auxiliary_space
                except Exception:
                    setattr(spaceDto2.MountedSpace, 'Space', auxiliary_space)
        else:
            try:
                if hasattr(context, 'AddMountedSpaceFromSpace'):
                    context.AddMountedSpaceFromSpace(auxiliary_space)
                if hasattr(context, 'RemoveSpace'):
                    context.RemoveSpace(spaceDto2.Space)
            except Exception:
                pass

        return True

    @dispatch(object, object, object, object)
    def switch_spaces(self, context:object, mounted_space1:object, mounted_space2:object, targetSpace2:object ):
        if mounted_space1 is None and mounted_space2 is None:
            return False
        
        auxiliary_space = mounted_space1.Space

        if mounted_space1 is not None:
            try:
                mounted_space1.Space = targetSpace2
            except Exception as e:
                print(f"Error switching mounted_space1.Space: {e}")
        else:
            
            context.AddMountedSpaceFromSpace(targetSpace2)
            context.removeSpace(mounted_space1.Space)

        if mounted_space2 is not None:
            mounted_space2.Space = auxiliary_space
        else:
            context.AddMountedSpaceFromSpace(auxiliary_space)
            context.removeSpace(mounted_space1.Space)

        return True
    
    # @dispatch(object, MountedSpace, MountedSpace)
    # def switch_spaces(self, context, mounted_space_a, mounted_space_b):
    #     """Swap the underlying Space between two mounted spaces (mounted-space variant).

    #     Faithful port of previous implementation: swap .Space values and log mappings.
    #     """
    #     try:
    #         a_num = getattr(getattr(mounted_space_a, 'Space', None), 'Number', getattr(getattr(mounted_space_a, 'Space', None), 'number', None))
    #         a_side = getattr(getattr(mounted_space_a, 'Space', None), 'Side', getattr(getattr(mounted_space_a, 'Space', None), 'side', None))
    #     except Exception:
    #         a_num = a_side = None

    #     try:
    #         b_num = getattr(getattr(mounted_space_b, 'Space', None), 'Number', getattr(getattr(mounted_space_b, 'Space', None), 'number', None))
    #         b_side = getattr(getattr(mounted_space_b, 'Space', None), 'Side', getattr(getattr(mounted_space_b, 'Space', None), 'side', None))
    #     except Exception:
    #         b_num = b_side = None

    #     self._write_log(f"SwitchSpaces BEFORE: A {a_side}/{a_num} <-> B {b_side}/{b_num}", context)

    #     # snapshot of mounted spaces mapping (number, side)
    #     try:
    #         before_map = [(getattr(getattr(ms, 'Space', None), 'Number', getattr(getattr(ms, 'Space', None), 'number', None)), getattr(getattr(ms, 'Space', None), 'Side', getattr(getattr(ms, 'Space', None), 'side', None))) for ms in getattr(context, 'mounted_spaces', []) or []]
    #         self._write_log(f"MountedSpaces mapping BEFORE: {before_map}", context)
    #     except Exception:
    #         pass

    #     # perform swap
    #     try:
    #         space_a = mounted_space_a.Space
    #         space_b = mounted_space_b.Space
    #         mounted_space_a.Space = space_b
    #         mounted_space_b.Space = space_a
    #     except Exception as e:
    #         self._write_log(f"SwitchSpaces ERROR swapping spaces: {e}", context)
    #         return False

    #     # after snapshot
    #     try:
    #         after_map = [(getattr(getattr(ms, 'Space', None), 'Number', getattr(getattr(ms, 'Space', None), 'number', None)), getattr(getattr(ms, 'Space', None), 'Side', getattr(getattr(ms, 'Space', None), 'side', None))) for ms in getattr(context, 'mounted_spaces', []) or []]
    #         self._write_log(f"SwitchSpaces AFTER: A {b_side}/{b_num} <-> B {a_side}/{a_num}; MountedSpaces mapping AFTER: {after_map}", context)
    #     except Exception:
    #         pass

    #     return True

    # PascalCase alias
    SwitchSpaces = switch_spaces

    def is_chopp_item(self) -> bool:
        """Return True if this item (or its product) is chopp/keg-type."""
        try:
            prod = getattr(self, 'product', None)
            if prod is not None:
                if hasattr(prod, 'is_chopp') and callable(getattr(prod, 'is_chopp')):
                    return bool(prod.is_chopp())
                return bool(getattr(prod, 'is_chopp', False) or getattr(self, 'is_chopp', False))
        except Exception:
            pass
        return bool(getattr(self, 'is_chopp', False))

    def is_isotonic_water_item(self) -> bool:
        """Return True if this item (or its product) is isotonic water."""
        try:
            prod = getattr(self, 'product', None)
            if prod is not None:
                if hasattr(prod, 'is_isotonic_water') and callable(getattr(prod, 'is_isotonic_water')):
                    return bool(prod.is_isotonic_water())
                return bool(getattr(prod, 'is_isotonic_water', False) or getattr(self, 'is_isotonic_water', False))
        except Exception:
            pass
        return bool(getattr(self, 'is_isotonic_water', False))

    def is_package_item(self) -> bool:
        """Return True if this item (or its product) is a package."""
        try:
            prod = getattr(self, 'product', None)
            if prod is not None:
                if hasattr(prod, 'is_package') and callable(getattr(prod, 'is_package')):
                    return bool(prod.is_package())
                return bool(getattr(prod, 'is_package', False) or getattr(self, 'is_package', False))
        except Exception:
            pass
        return bool(getattr(self, 'is_package', False))

    def is_box_template_item(self) -> bool:
        """Return True if this item (or its product) is a box template."""
        try:
            prod = getattr(self, 'product', None)
            if prod is not None:
                if hasattr(prod, 'is_box_template') and callable(getattr(prod, 'is_box_template')):
                    return bool(prod.is_box_template())
                return bool(getattr(prod, 'is_box_template', False) or getattr(self, 'is_box_template', False))
        except Exception:
            pass
        return bool(getattr(self, 'is_box_template', False))

    def is_layer_item(self) -> bool:
        """Return True if this item is a layer product/item."""
        try:
            prod = getattr(self, 'product', None)
            if prod is not None:
                if hasattr(prod, 'is_layer') and callable(getattr(prod, 'is_layer')):
                    return bool(prod.is_layer())
                return bool(getattr(prod, 'is_layer', False) or getattr(self, 'is_layer', False))
        except Exception:
            pass
        return bool(getattr(self, 'is_layer', False))

    def is_marketplace_item(self) -> bool:
        """Return True if this item (or its product) is a marketplace item."""
        try:
            prod = getattr(self, 'product', None)
            if prod is not None:
                if hasattr(prod, 'is_marketplace') and callable(getattr(prod, 'is_marketplace')):
                    return bool(prod.is_marketplace())
                return bool(getattr(prod, 'is_marketplace', False) or getattr(self, 'is_marketplace', False))
        except Exception:
            pass
        return bool(getattr(self, 'is_marketplace', False))