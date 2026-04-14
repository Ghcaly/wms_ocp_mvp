from ...domain.space_size import SpaceSize
from ...domain.space import Space
from ...domain.mounted_space_list import MountedSpaceList
from ...domain.space_list import SpaceList
from ...domain.base_rule import BaseRule
from ...domain.context import Context
from dataclasses import dataclass


@dataclass
class SpaceWithMountedSpaceDto:
    Space: object
    MountedSpace: object


class SideBalanceRule(BaseRule):
    def __init__(self):
        super().__init__(name='SideBalanceRule')

    def should_execute(self, context: Context) -> bool:
        if not context.get_setting('SideBalanceRule', False):
            context.add_execution_log('Regra desativada, nao sera executada')
            return False
        if not getattr(context, 'mounted_spaces', None):
            context.add_execution_log('Nenhuma baia montada, a regra nao sera executada')
            return False
        return True

    def execute(self, context: Context) -> Context:
        context.add_execution_log('Iniciando execucao da regra')

        percentage = self._get_percentage_weight_of_driver_side(context)
        context.add_execution_log(
            f'Inicio do balanceamento - Lado Motorista: {percentage:.2f}% - Lado Ajudante: {100.0 - percentage:.2f}%'
        )
        context.add_execution_log(self._get_pallet_weight_log_message(context))

        mounted_spaces = MountedSpaceList(context.MountedSpaces).OrderByWeightDesc()
        self._side_balance(context, mounted_spaces)

        self._ensure_driver_side_weight_is_greater(context)

        percentage = self._get_percentage_weight_of_driver_side(context)
        context.add_execution_log(
            f'Fim do balanceamento - Lado Motorista: {percentage:.2f}% - Lado Ajudante: {100.0 - percentage:.2f}%'
        )
        context.add_execution_log(self._get_pallet_weight_log_message(context))

        return context

    def _side_balance(self, context: Context, mounted_spaces):
        """
        Port fiel do C# SideBalance:
        Para cada mounted space (ordem decrescente de peso),
        encontra o primeiro space não balanceado que caiba o conteúdo,
        e troca os espaços.
        """
        for mounted_space in mounted_spaces:
            is_driver_side = self._is_driver_side(context)
            target_space = self._get_first_space_not_balanced(context, mounted_space, is_driver_side)
            if target_space is None:
                side_str = getattr(getattr(mounted_space, 'Space', mounted_space), 'Side',
                                   getattr(getattr(mounted_space, 'space', None), 'side', '?'))
                num_str = getattr(getattr(mounted_space, 'Space', mounted_space), 'Number',
                                  getattr(getattr(mounted_space, 'space', None), 'number', '?'))
                weight = getattr(mounted_space, 'weight', 0)
                context.add_execution_log(
                    f'Nenhuma baia encontrada para balancear os produtos da Baia:{side_str}/{num_str} - Peso:{weight:.2f}'
                )
                continue

            target_mounted_space = context.get_mounted_space(target_space)

            if (target_mounted_space is None or
                    self._get_mounted_space_occupation(
                        target_mounted_space, mounted_space.space.size,
                        context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
                    ) <= mounted_space.space.size):
                self._switch_spaces_and_set_balanced(context, mounted_space, target_space)
            else:
                self._search_new_space_to_switch(context, mounted_space, target_mounted_space, target_space, is_driver_side)

    def _is_driver_side(self, context: Context) -> bool:
        """
        C#: driverBalancedWeight <= helperBalancedWeight
        """
        try:
            balanced = context.GetMountedSpacesBalanced()
            driver = sum(x.weight for x in MountedSpaceList(balanced).DriverSide())
            helper = sum(x.weight for x in MountedSpaceList(balanced).HelperSide())
            return driver <= helper
        except Exception as e:
            print("Error determining driver side:", e)
            return True

    def _get_first_space_not_balanced(self, context, mounted_space, is_driver_side):
        """
        C#:
        context.GetAllSpaces()
               .NotBalanced()
               .Where(x => x.Size >= GetMountedSpaceOccupation(mountedSpace, x.Size, ...))
               .OrderByDescending(x => x.IsDriverSide() == isDriverSide)
               .ThenBy(x => x.Number)
               .FirstOrDefault()
        """
        spaces = SpaceList(context.GetAllSpaces()).NotBalanced().spaces
        spaces = [
            s for s in spaces
            if float(s.size) >= self._get_mounted_space_occupation(
                mounted_space, s.size,
                context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
            )
        ]
        spaces_sorted = sorted(
            spaces,
            key=lambda s: (
                -(s.is_driver_side() == is_driver_side),  # DESC: matching side first
                s.number                                   # ASC
            )
        )
        return spaces_sorted[0] if spaces_sorted else None

    def _switch_spaces_and_set_balanced(self, context: Context, mounted_space, target_space):
        """
        C#: SwitchSpacesAndSetBalanced
        """
        target_mounted_space = context.get_mounted_space(target_space)

        is_different = (mounted_space.Space.Number != target_space.Number or
                        mounted_space.Space.Side != target_space.Side)
        if is_different:
            context.add_execution_log(
                f'Movendo os produtos da Baia:{mounted_space.Space.Side}/{mounted_space.Space.Number} '
                f'para a Baia:{target_space.Side}/{target_space.Number}'
            )
            current_dto = SpaceWithMountedSpaceDto(Space=mounted_space.Space, MountedSpace=mounted_space)
            target_dto = SpaceWithMountedSpaceDto(Space=target_space, MountedSpace=context.get_mounted_space(target_space))
            context.domain_operations.switch_spaces(context, current_dto, target_dto)
            target_mounted_space = context.get_mounted_space(target_space)

        self._recalculate_mounted_space_occupation(context, target_mounted_space)
        self._adjust_closed_pallet(context, target_mounted_space)

        try:
            target_space.SetBalanced()
        except Exception:
            try:
                target_space.set_balanced()
            except Exception:
                pass

    def _switch_spaces(self, context: Context, space, target_space):
        """
        C#: SwitchSpaces (helper that logs and calls operations)
        """
        current_ms = context.get_mounted_space(space)
        target_ms = context.get_mounted_space(target_space)
        context.add_execution_log(
            f'Movendo os produtos da Baia:{space.Side}/{space.Number} '
            f'para a Baia:{target_space.Side}/{target_space.Number}'
        )
        current_dto = SpaceWithMountedSpaceDto(Space=space, MountedSpace=current_ms)
        target_dto = SpaceWithMountedSpaceDto(Space=target_space, MountedSpace=target_ms)
        context.domain_operations.switch_spaces(context, current_dto, target_dto)

    def _ensure_driver_side_weight_is_greater(self, context: Context):
        """
        Port fiel do C# EnsureDriverSideWeightIsGreater.
        Se ajudante > motorista: itera TODOS os helper spaces em ordem crescente de número
        e troca cada um com o driver space correspondente (mesmo número).
        Não há break antecipado — todos os pares são trocados.
        """
        driver = sum(x.weight for x in MountedSpaceList(context.MountedSpaces).DriverSide())
        helper = sum(x.weight for x in MountedSpaceList(context.MountedSpaces).HelperSide())

        if helper > driver:
            context.add_execution_log('Lado do Ajudante com peso maior que o Lado do Motorista, invertendo as baias')

            all_spaces = context.GetAllSpaces()
            helper_spaces = sorted(
                [s for s in all_spaces if not s.is_driver_side()],
                key=lambda s: s.number
            )

            for helper_space in helper_spaces:
                target_space = next(
                    (s for s in all_spaces if s.is_driver_side() and s.number == helper_space.number),
                    None
                )
                if target_space is None:
                    continue

                current_ms = context.get_mounted_space(helper_space)
                target_ms = context.get_mounted_space(target_space)
                current_dto = SpaceWithMountedSpaceDto(Space=helper_space, MountedSpace=current_ms)
                target_dto = SpaceWithMountedSpaceDto(Space=target_space, MountedSpace=target_ms)
                context.domain_operations.switch_spaces(context, current_dto, target_dto)
                context.add_execution_log(
                    f'Invertendo Baia:{helper_space.Side}/{helper_space.number} '
                    f'com Baia:{target_space.Side}/{target_space.number}'
                )

    def _search_new_space_to_switch(self, context: Context, mounted_space, target_mounted_space, target_space, is_driver_side):
        if self._try_switch_target_mounted_space_to_empty_space(context, mounted_space, target_mounted_space, target_space, is_driver_side):
            return
        if self._try_switch_target_space_to_another_mounted_space(context, mounted_space, target_mounted_space, target_space, is_driver_side):
            return
        self._find_new_space_with_same_size_spaces(context, mounted_space, is_driver_side)

    def _try_switch_target_mounted_space_to_empty_space(self, context: Context, mounted_space, target_mounted_space, target_space, is_driver_side):
        """
        C#: context.Spaces.Where(x => x.Size >= GetMountedSpaceOccupation(targetMountedSpace, x.Size, ...))
        """
        available = [
            s for s in getattr(context, 'spaces', []) or []
            if float(s.size) >= self._get_mounted_space_occupation(
                target_mounted_space, s.size,
                context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
            )
        ]
        if available:
            space_to_switch = self._find_best_space_to_switch(available, is_driver_side)
            self._switch_spaces(context, target_space, space_to_switch)
            self._switch_spaces_and_set_balanced(context, mounted_space, target_space)
            return True
        return False

    def _try_switch_target_space_to_another_mounted_space(self, context: Context, mounted_space, target_mounted_space, target_space, is_driver_side):
        """
        C#: context.MountedSpaces.Where(...).Select(x => x.Space).NotBalanced()
        """
        candidates = []
        for x in getattr(context, 'mounted_spaces', []) or []:
            if x.Space != mounted_space.Space and x.Space != target_space:
                occ_in_ms_size = self._get_mounted_space_occupation(
                    x, mounted_space.space.size,
                    context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
                )
                occ_target_in_x_size = self._get_mounted_space_occupation(
                    target_mounted_space, x.Space.size,
                    context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
                )
                if occ_in_ms_size <= mounted_space.space.size and x.Space.size >= occ_target_in_x_size:
                    candidates.append(x.Space)

        candidates = SpaceList(candidates).NotBalanced().spaces
        if candidates:
            space_to_switch = self._find_best_space_to_switch(candidates, is_driver_side)
            self._switch_spaces(context, target_space, space_to_switch)
            self._switch_spaces_and_set_balanced(context, mounted_space, target_space)
            return True
        return False

    def _find_new_space_with_same_size_spaces(self, context: Context, mounted_space, is_driver_side):
        """
        C#: context.GetAllSpaces().Where(space => space.Size == mountedSpace.Space.Size).NotBalanced()
        """
        same_size = (
            SpaceList(context.GetAllSpaces())
            .matching(lambda x: x.size == mounted_space.space.size)
            .NotBalanced()
        )
        new_target = self._find_best_space_to_switch(same_size, is_driver_side)
        if new_target:
            self._switch_spaces_and_set_balanced(context, mounted_space, new_target)

    def _find_best_space_to_switch(self, spaces, is_driver_side):
        """
        C#: OrderByDescending(space => space.IsDriverSide() == isDriverSide).ThenBy(space => space.Number).FirstOrDefault()
        """
        try:
            return SpaceList(spaces).OrderByDescending(
                lambda space: space.IsDriverSide() == is_driver_side
            ).ThenBy(lambda space: space.Number).FirstOrDefault()
        except Exception as e:
            print(f"Error finding best space: {e}")
            return spaces[0] if spaces else None

    def _get_mounted_space_occupation(self, mounted_space, size, calculate_additional_occupation):
        """
        C#: if same size → return Occupation; else use FactorConverter
        """
        try:
            if mounted_space.space.size == size:
                return mounted_space.Occupation

            calculate_additional_occupation = (
                not mounted_space.GetFirstPallet().Bulk and calculate_additional_occupation
            )
            from ...domain.factor_converter import FactorConverter
            fc = FactorConverter()
            mounted_products = mounted_space.GetProducts()
            total = 0
            for mp in mounted_products:
                occ = fc.occupation(mp, size, getattr(mp, 'item', None), calculate_additional_occupation)
                total += float(occ)
            return total
        except Exception as e:
            print(f"Error getting mounted space occupation: {e}")
            return getattr(mounted_space, 'occupation', 0)

    def _get_percentage_weight_of_driver_side(self, context: Context) -> float:
        """
        C#: driverSideWeight * 100 / totalWeight
        """
        total_weight = sum(ms.weight for ms in context.mounted_spaces)
        driver_weight = sum(ms.weight for ms in MountedSpaceList(context.mounted_spaces).DriverSide())
        return float((driver_weight * 100 / total_weight) if total_weight != 0 else 0.0)

    def _recalculate_mounted_space_occupation(self, context: Context, mounted_space):
        """
        C#: RecalculeMountedSpaceOccupation
        """
        try:
            old = mounted_space.occupation
            mounted_space.SetOccupation(0)
            for mp in mounted_space.get_products():
                try:
                    mp.Item.SetAdditionalOccupation(0)
                except Exception:
                    pass
                occ = self._get_product_total_occupation(
                    mounted_space, mp,
                    context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
                )
                mountedProductOccupation = occ - mp.Item.AdditionalOccupation
                mp.SetOccupation(mountedProductOccupation)
                mounted_space.IncreaseOccupation(occ)
            context.add_execution_log(
                f'Recalculado ocupação da Baia:{getattr(mounted_space.space, "Side", "?")}/{getattr(mounted_space.space, "Number", "?")} '
                f'- Antes:{old:.2f} - Depois:{getattr(mounted_space, "Occupation", 0):.2f}'
            )
        except Exception as e:
            print("Error recalculating mounted space occupation:", e)

    def _get_product_total_occupation(self, mounted_space, mounted_product, calculate_additional_occupation):
        """
        C#: GetProductTotalOccupation
        """
        try:
            if mounted_space.GetFirstPallet().Bulk:
                return float(mounted_space.space.size)
            factor = mounted_product.Product.get_factor(mounted_space.space.size)
            from ...domain.factor_converter import FactorConverter
            fc = FactorConverter()
            return fc.occupation(
                getattr(mounted_product, 'Amount', getattr(mounted_product, 'amount', 0)),
                factor,
                mounted_product.Product.PalletSetting,
                mounted_product.Item,
                calculate_additional_occupation
            )
        except Exception as e:
            print(f"Error getting product total occupation: {e}")
            return 0

    def _adjust_closed_pallet(self, context: Context, mounted_space):
        """
        C#: AdjusteClosedPallet
        """
        try:
            old = mounted_space.GetFirstPallet().Bulk
            if mounted_space.GetFirstPallet().Bulk and mounted_space.space.size < SpaceSize.Size42:
                mounted_space.GetFirstPallet().SetBulk(context.get_setting('BulkAllPallets', False))
            context.add_execution_log(
                f'Recalculando palete fechado da Baia:{getattr(mounted_space.Space, "Side", "?")}/{getattr(mounted_space.Space, "Number", "?")} '
                f'- Antes: {old} - Depois: {mounted_space.GetFirstPallet().Bulk}'
            )
        except Exception as e:
            print(f"Error adjusting closed pallet: {e}")

    def _get_pallet_weight_log_message(self, context: Context) -> str:
        """
        C#: GetPalletWeightLogMessage — ordered by Space.Number
        """
        parts = []
        for ms in sorted(getattr(context, 'mounted_spaces', []) or [],
                         key=lambda x: getattr(getattr(x, 'Space', x), 'Number',
                                               getattr(getattr(x, 'space', None), 'number', 0))):
            side = getattr(getattr(ms, 'Space', ms), 'Side',
                           getattr(getattr(ms, 'space', None), 'side', '?'))
            number = getattr(getattr(ms, 'Space', ms), 'Number',
                             getattr(getattr(ms, 'space', None), 'number', '?'))
            weight = getattr(ms, 'Weight', getattr(ms, 'weight', 0)) or 0
            parts.append(f"{side}/{number} weight: {weight:.2f}")
        return '; '.join(parts)
