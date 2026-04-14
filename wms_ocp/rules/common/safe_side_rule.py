from ...domain.truck_safe_side import TruckSafeSide
from ...domain.truck_bay_side import TruckBaySide
from ...domain.base_rule import BaseRule
from ...domain.context import Context
from ...domain.calculator_constants import CalculatorConstants
from ...domain.factor_converter import FactorConverter
from typing import List, Iterable, Optional
from dataclasses import dataclass, field
import itertools


@dataclass
class MountedSpaceIdDto:
    MountedSpaceId: int
    MountedSpace: object
    SafeDriverCurrentOccupation: float
    IndifferentOccupation: float


@dataclass
class SafeSideCombinationDto:
    Space: object
    MountedSpace: object
    MountedSpaceId: int
    SafeHelperOccupation: float = 0.0
    IndifferentOccupation: float = 0.0

    def is_chopp(self) -> bool:
        """Mirrors C# SafeSideCombinationDto.IsChopp() extension:
        checks if the mounted space's first pallet product base is Chopp."""
        try:
            first_pallet = self.MountedSpace.GetFirstPallet()
            if first_pallet is None:
                return False
            pb = getattr(first_pallet, 'ProductBase', None)
            if pb is None:
                return False
            return hasattr(pb, 'is_chopp') and pb.is_chopp()
        except Exception:
            return False


class SafeSideRule(BaseRule):
    def __init__(self, factor_converter: FactorConverter = None):
        super().__init__(name='SafeSideRule')
        self._factor_converter = factor_converter or FactorConverter()
        self.TotalOccupation = 0.0

    def should_execute(self, context: Context) -> bool:
        if not context.get_setting('EnableSafeSideRule'):
            context.add_execution_log('Regra desativada, nao sera executada')
            return False

        # Mirrors C#: context is ICrossDockingRuleContext || context is IASRuleContext || context is IMixedRuleContext
        # In Python ASRuleContext is the base for CrossDocking, Mixed and T4 contexts
        from ...domain.context import ASRuleContext
        if isinstance(context, ASRuleContext):
            context.add_execution_log(
                f'Mapa {context.MapNumber}, Mapas do tipo {type(context).__name__} nao executam regra de lado seguro'
            )
            return False

        # Mirrors C#: context.Spaces.Count + context.MountedSpaces.Count
        total_bays = len(context.Spaces) + len(context.MountedSpaces)

        if total_bays <= CalculatorConstants.SAFE_SIDE_RULE_MIN_TRUCK_BAYS:
            context.add_execution_log(
                f'Mapa {context.MapNumber}, O veiculo deve ter mais de {CalculatorConstants.SAFE_SIDE_RULE_MIN_TRUCK_BAYS} baias'
            )
            return False

        if total_bays > CalculatorConstants.SAFE_SIDE_RULE_MAX_TRUCK_BAYS:
            context.add_execution_log(
                f'Mapa {context.MapNumber}, O veiculo nao pode ter mais de {CalculatorConstants.SAFE_SIDE_RULE_MAX_TRUCK_BAYS} baias'
            )
            return False

        if not context.GetDeliveriesHelperSafeSide():
            context.add_execution_log(
                f'O mapa {context.MapNumber} nao tem cliente com o lado seguro de ajudante configurado'
            )
            return False

        return True

    def execute(self, context: Context) -> Context:
        context.add_execution_log('Iniciando execucao da regra')

        self._seed_delivery_order_amount(context)

        mounted_spaces_id: List[MountedSpaceIdDto] = []
        for idx, ms in enumerate(context.mounted_spaces):
            safe_driver = sum(
                self._factor_converter.occupation(
                    z.GetSideQuantity(TruckSafeSide.DRIVER), ms.space.size, z.item,
                    context.get_setting('OccupationAdjustmentToPreventExcessHeight')
                ) for z in ms.get_products()
            )
            indifferent = sum(
                self._factor_converter.occupation(
                    z.GetSideQuantity(TruckSafeSide.INDIFFERENT), ms.space.size, z.item,
                    context.get_setting('OccupationAdjustmentToPreventExcessHeight')
                ) for z in ms.get_products()
            )
            mounted_spaces_id.append(MountedSpaceIdDto(
                MountedSpaceId=idx,
                MountedSpace=ms,
                SafeDriverCurrentOccupation=safe_driver,
                IndifferentOccupation=indifferent
            ))

        spaces = list(context.get_all_spaces())
        self.TotalOccupation = sum(
            sum(
                self._factor_converter.occupation(
                    y, ms.space.size, y.item,
                    context.get_setting('OccupationAdjustmentToPreventExcessHeight')
                ) for y in ms.get_products()
            ) for ms in context.mounted_spaces
        )
        initial_score = self._get_initial_score(context)

        max_bay_number = max((s.Number for s in spaces), default=0)

        # Build helper side options
        helper_side_options: List[List[SafeSideCombinationDto]] = []
        for space in spaces:
            if not space.IsHelperSide():
                continue
            choices = []
            for mounted in mounted_spaces_id:
                total_ocp = sum(
                    self._factor_converter.occupation(
                        z, space.size, z.item,
                        context.get_setting('OccupationAdjustmentToPreventExcessHeight')
                    ) for z in mounted.MountedSpace.GetProducts()
                )
                if total_ocp <= space.size:
                    choices.append(SafeSideCombinationDto(
                        Space=space,
                        MountedSpace=mounted.MountedSpace,
                        MountedSpaceId=mounted.MountedSpaceId,
                        SafeHelperOccupation=sum(
                            self._factor_converter.occupation(
                                z.GetSideQuantity(TruckSafeSide.HELPER), space.size, z.item,
                                context.get_setting('OccupationAdjustmentToPreventExcessHeight')
                            ) for z in mounted.MountedSpace.GetProducts()
                        ),
                        IndifferentOccupation=sum(
                            self._factor_converter.occupation(
                                z.GetSideQuantity(TruckSafeSide.INDIFFERENT), space.size, z.item,
                                context.get_setting('OccupationAdjustmentToPreventExcessHeight')
                            ) for z in mounted.MountedSpace.GetProducts()
                        )
                    ))
            helper_side_options.append(choices)

        helper_combination = self._get_helper_side_combination(
            context, max_bay_number, initial_score, helper_side_options, mounted_spaces_id
        )
        if not helper_combination:
            context.add_execution_log(
                f'Mapa {context.MapNumber}, Nenhuma combinacao melhor encontrada, finalizando execucao da regra.'
            )
            return context

        used_mounted_spaces = [c.MountedSpace for c in helper_combination]

        drive_side_options: List[List[SafeSideCombinationDto]] = []
        for space in spaces:
            if not space.IsDriverSide():
                continue
            choices = []
            for mounted in mounted_spaces_id:
                if mounted.MountedSpace in used_mounted_spaces:
                    continue
                total_ocp = sum(
                    self._factor_converter.occupation(
                        z, space.size, z.item,
                        context.get_setting('OccupationAdjustmentToPreventExcessHeight')
                    ) for z in mounted.MountedSpace.GetProducts()
                )
                if total_ocp <= space.size:
                    choices.append(SafeSideCombinationDto(
                        Space=space,
                        MountedSpace=mounted.MountedSpace,
                        MountedSpaceId=mounted.MountedSpaceId
                    ))
            drive_side_options.append(choices)

        driver_combination = self._get_driver_side_combination(context, max_bay_number, drive_side_options)
        if not driver_combination:
            context.add_execution_log(
                f'Mapa {context.MapNumber}, Nao foi possivel achar uma opcao para o lado motorista, finalizando execucao da regra.'
            )
            return context

        # Mirrors C# ApplySafeSideChanges — note: uses capital .Space (dataclass field)
        for item in helper_combination:
            item.MountedSpace.SetSpace(item.Space)
        for item in driver_combination:
            item.MountedSpace.SetSpace(item.Space)

        self._get_final_score(context)
        context.add_execution_log('Finalizado a execucao da regra')
        return context

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _seed_delivery_order_amount(self, context: Context) -> None:
        complex_delivery_order = context.GetComplexDeliveryOrder()

        indifferent = context.GetDeliveriesIndifferentSafeSide()
        self._log_delivery_orders(context, indifferent, TruckSafeSide.INDIFFERENT)

        helper = context.GetDeliveriesHelperSafeSide()
        self._log_delivery_orders(context, helper, TruckSafeSide.HELPER)

        driver = context.GetDeliveriesDriverSafeSide()
        self._log_delivery_orders(context, driver, TruckSafeSide.DRIVER)

        self._seed_delivery_order_amount_per_side(
            context, TruckBaySide.HELPER, complex_delivery_order, indifferent, helper, driver
        )
        self._seed_delivery_order_amount_per_side(
            context, TruckBaySide.DRIVER, complex_delivery_order, indifferent, helper, driver
        )

    def _log_delivery_orders(self, context: Context, deliveries: Iterable[int], safe_side) -> None:
        s = ', '.join(str(d) for d in deliveries)
        context.add_execution_log(f'Safe Side: {safe_side} - Deliveries: {s}')

    def _seed_delivery_order_amount_per_side(
        self,
        context: Context,
        truck_side: TruckBaySide,
        complex_delivery_order: int,
        indifferent_deliveries: Iterable[int],
        helper_deliveries: Iterable[int],
        driver_deliveries: Iterable[int]
    ) -> None:
        # Mirrors C#:
        # context.MountedSpaces.Where(x => side == truckSide)
        #   .SelectMany(x => x.GetProducts().WithAmount().OrderByAssemblySequence())
        indifferent_set = set(indifferent_deliveries)
        helper_set = set(helper_deliveries)
        driver_set = set(driver_deliveries)

        mounted_products = []
        for ms in context.mounted_spaces:
            if getattr(ms.space, 'Side', None) == truck_side:
                # WithAmount() — only products with Amount > 0
                products_with_amount = [p for p in ms.get_products() if getattr(p, 'Amount', 0) > 0]
                # OrderByAssemblySequence()
                products_with_amount.sort(key=lambda p: getattr(p, 'AssemblySequence', 0))
                mounted_products.extend(products_with_amount)

        is_helper_side = (truck_side == TruckBaySide.HELPER)

        for mp in mounted_products:
            total_amount = mp.Amount
            item = mp.item

            # Mirrors C# LINQ ordering:
            # .OrderByDescending(x => x == complexDeliveryOrder)
            # .ThenByDescending(x => truckSide == Helper ? helperDeliveries.Contains(x) : driverDeliveries.Contains(x))
            # .ThenByDescending(x => indifferentDeliveries.Contains(x))
            def sort_key(x):
                is_complex = (x == complex_delivery_order)
                is_preferred_side = (x in helper_set) if is_helper_side else (x in driver_set)
                is_indifferent = (x in indifferent_set)
                return (is_complex, is_preferred_side, is_indifferent)

            delivery_orders = sorted(item.DeliveryOrdersWithAmount(), key=sort_key, reverse=True)

            for delivery_order in delivery_orders:
                if total_amount <= 0:
                    break
                if (not mp.ComplexLoad) and delivery_order == complex_delivery_order:
                    continue
                amount_of_delivery = item.SubtractDeliveryOrderAmount(delivery_order, total_amount)
                total_amount -= amount_of_delivery
                mp.AddDeliveryOrderQuantity(delivery_order, amount_of_delivery)

    def _get_initial_score(self, context: Context) -> float:
        return self._get_score(context, 'Inicial')

    def _get_final_score(self, context: Context) -> float:
        return self._get_score(context, 'Final')

    def _get_score(self, context: Context, score_log_text: str) -> float:
        adj = context.get_setting('OccupationAdjustmentToPreventExcessHeight')

        helper_safe = sum(
            self._factor_converter.occupation(z.GetSideQuantity(TruckSafeSide.HELPER), y.space.size, z.item, adj)
            for y in context.mounted_spaces if y.space.IsHelperSide()
            for z in y.get_products() if getattr(z, 'Amount', 0) > 0
        )
        driver_safe = sum(
            self._factor_converter.occupation(z.GetSideQuantity(TruckSafeSide.DRIVER), y.space.size, z.item, adj)
            for y in context.mounted_spaces if y.space.IsDriverSide()
            for z in y.get_products() if getattr(z, 'Amount', 0) > 0
        )
        indifferent = sum(
            self._factor_converter.occupation(z.GetSideQuantity(TruckSafeSide.INDIFFERENT), y.space.size, z.item, adj)
            for y in context.mounted_spaces
            for z in y.get_products() if getattr(z, 'Amount', 0) > 0
        )

        total_safe = helper_safe + driver_safe + indifferent
        score = (total_safe / self.TotalOccupation) if self.TotalOccupation != 0 else 0
        context.add_execution_log(
            f'Mapa {context.MapNumber} - Score {score_log_text}({score:.2f})Pts; '
            f'Ocupacao Segura({total_safe:.2f}); Ocupacao Total({self.TotalOccupation:.2f}).'
        )
        return score

    # ------------------------------------------------------------------ #
    # Combination builders — mirrors C# GetHelperSideCombination /        #
    # GetDriverSideCombination                                             #
    # ------------------------------------------------------------------ #

    def _get_helper_side_combination(
        self,
        context: Context,
        max_bay_number: int,
        initial_score: float,
        helper_side_options: List[List[SafeSideCombinationDto]],
        mounted_spaces_id: List[MountedSpaceIdDto]
    ) -> Optional[List[SafeSideCombinationDto]]:
        # Mirrors C# GetCombinationsGroup
        combinations = self._get_combinations_group(helper_side_options)
        # Mirrors C# FilterValidCombinations (load balance + chopp position)
        combinations = self._filter_valid_combinations(context, max_bay_number, combinations)
        # Mirrors C# GetBetterCombination
        return self._get_better_combination(combinations, initial_score, mounted_spaces_id)

    def _get_driver_side_combination(
        self,
        context: Context,
        max_bay_number: int,
        drive_side_options: List[List[SafeSideCombinationDto]]
    ) -> Optional[List[SafeSideCombinationDto]]:
        # Mirrors C# GetCombinationsGroup
        combinations = self._get_combinations_group(drive_side_options)
        # Mirrors C# FilterValidCombinations (load balance + chopp position)
        combinations = self._filter_valid_combinations(context, max_bay_number, combinations)
        # Mirrors C# FirstOrDefault()
        return next(iter(combinations), None)

    @staticmethod
    def _get_combinations_group(
        sequences: List[List[SafeSideCombinationDto]]
    ) -> List[List[SafeSideCombinationDto]]:
        """Mirrors C# GetCombinationsGroup: cartesian product excluding combos with repeated MountedSpaceId."""
        if not sequences:
            return [[]]
        valid = []
        for combo in itertools.product(*sequences):
            ids = [c.MountedSpaceId for c in combo]
            if len(ids) == len(set(ids)):
                valid.append(list(combo))
        return valid

    def _filter_valid_combinations(
        self,
        context: Context,
        max_bay_number: int,
        combinations: List[List[SafeSideCombinationDto]]
    ) -> List[List[SafeSideCombinationDto]]:
        """Mirrors C# FilterValidCombinations."""
        combinations = self._filter_valid_load_balance(context, combinations)
        combinations = self._filter_valid_chopp_position(context, max_bay_number, combinations)
        return combinations

    @staticmethod
    def _filter_valid_load_balance(
        context: Context,
        combinations: List[List[SafeSideCombinationDto]]
    ) -> List[List[SafeSideCombinationDto]]:
        """Mirrors C# FilterValidLoadBalance:
        keeps combinations where the side weight fraction is within [30%, 70%]."""
        total_weight = sum(
            getattr(ms, 'Weight', 0) for ms in context.mounted_spaces
        )
        if total_weight == 0:
            return combinations
        return [
            combo for combo in combinations
            if (CalculatorConstants.MINIMUM_VALID_DISTRIBUTION_PER_SIDE
                <= sum(getattr(c.MountedSpace, 'Weight', 0) for c in combo) / total_weight
                <= CalculatorConstants.MAXIMUM_VALID_DISTRIBUTION_PER_SIDE)
        ]

    @staticmethod
    def _filter_valid_chopp_position(
        context: Context,
        max_bay_number: int,
        combinations: List[List[SafeSideCombinationDto]]
    ) -> List[List[SafeSideCombinationDto]]:
        """Mirrors C# FilterValidChoppPosition:
        ensures chopp pallets are placed at the rear bays of the truck."""
        chopp_count = sum(
            1 for ms in context.mounted_spaces
            if (fp := ms.GetFirstPallet()) is not None
            and getattr(fp, 'ProductBase', None) is not None
            and hasattr(fp.ProductBase, 'is_chopp')
            and fp.ProductBase.is_chopp()
        )
        if chopp_count == 0:
            return combinations

        must_have = chopp_count // 2
        could_have = chopp_count % 2

        # Cant Have: no chopp in front bays
        combinations = [
            combo for combo in combinations
            if not any(
                c.is_chopp() and getattr(c.Space, 'Number', 0) <= (max_bay_number - must_have - could_have)
                for c in combo
            )
        ]
        # Must Have: enough chopp in rear bays
        combinations = [
            combo for combo in combinations
            if sum(
                1 for c in combo
                if c.is_chopp() and getattr(c.Space, 'Number', 0) > (max_bay_number - must_have)
            ) >= must_have
        ]

        return combinations

    def _get_better_combination(
        self,
        combinations: List[List[SafeSideCombinationDto]],
        initial_score: float,
        mounted_spaces: List[MountedSpaceIdDto]
    ) -> Optional[List[SafeSideCombinationDto]]:
        """Mirrors C# GetBetterCombination: filters by score > initialScore then picks highest."""
        total = self.TotalOccupation or 1

        def score_of(combo):
            combo_ms = {c.MountedSpaceId for c in combo}
            return (
                sum(c.SafeHelperOccupation + c.IndifferentOccupation for c in combo)
                + sum(
                    m.SafeDriverCurrentOccupation + m.IndifferentOccupation
                    for m in mounted_spaces if m.MountedSpaceId not in combo_ms
                )
            ) / total

        # Mirrors C# FilterBestScoreCombination: only combos that beat initialScore
        better = [combo for combo in combinations if score_of(combo) > initial_score]

        if not better:
            return None

        return max(better, key=score_of)
