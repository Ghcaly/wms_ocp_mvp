from ...domain.truck_safe_side import TruckSafeSide
from ...domain.truck_bay_side import TruckBaySide
from ...domain.base_rule import BaseRule
from ...domain.context import Context
from ...domain.calculator_constants import CalculatorConstants
from ...domain.factor_converter import FactorConverter
from typing import List, Iterable, Optional
from dataclasses import dataclass
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


class SafeSideRule(BaseRule):
    def __init__(self, factor_converter: FactorConverter = None):
        super().__init__(name='SafeSideRule')
        self._factor_converter = factor_converter or FactorConverter()
        self.TotalOccupation = 0.0

    def should_execute(self, context: Context) -> bool:
        if not context.get_setting('EnableSafeSideRule'):
            context.add_execution_log('Regra desativada, nao sera executada')
            return False

        # skip crossdock / as / mixed contexts (mirrors C# SafeSideRule.ShouldExecute)
        if getattr(context, '_kind', getattr(context, 'Kind', '')) in ('AS', 'CrossDocking', 'Mixed'):
            context.add_execution_log(f'Mapa {context.MapNumber}, tipo {context.Kind} nao executa regra de lado seguro')
            return False

        if (len(context.get_all_spaces())) <= CalculatorConstants.SAFE_SIDE_RULE_MIN_TRUCK_BAYS:
            context.add_execution_log(f'Mapa {context.MapNumber}, O veiculo deve ter mais de {CalculatorConstants.SAFE_SIDE_RULE_MIN_TRUCK_BAYS} baias')
            return False

        if (len(context.get_all_spaces())) > CalculatorConstants.SAFE_SIDE_RULE_MAX_TRUCK_BAYS:
            context.add_execution_log(f'Mapa {context.MapNumber}, O veiculo nao pode ter mais de {CalculatorConstants.SAFE_SIDE_RULE_MAX_TRUCK_BAYS} baias')
            return False

        if not context.GetDeliveriesHelperSafeSide():
            context.add_execution_log(f'O mapa {context.MapNumber} nao tem cliente com o lado seguro de ajudante configurado')
            return False

        return True

    def execute(self, context: Context) -> Context:
        context.add_execution_log('Iniciando execucao da regra')

        # Seed and prepare
        self._seed_delivery_order_amount(context)

        # Build mountedSpacesId dto list
        mounted_spaces_id: List[MountedSpaceIdDto] = []  
        for idx, ms in enumerate(context.mounted_spaces):
            safe_driver = sum(self._factor_converter.occupation(z.GetSideQuantity('Driver'), ms.space.size, z.item, context.get_setting('OccupationAdjustmentToPreventExcessHeight')) for z in ms.get_products())
            indifferent = sum(self._factor_converter.occupation(z.GetSideQuantity('Indifferent'), ms.space.size, z.item, context.get_setting('OccupationAdjustmentToPreventExcessHeight') ) for z in ms.get_products())
            mounted_spaces_id.append(MountedSpaceIdDto(MountedSpaceId=idx, MountedSpace=ms, SafeDriverCurrentOccupation=safe_driver, IndifferentOccupation=indifferent))

        spaces = list(context.get_all_spaces())
        self.TotalOccupation = sum(sum(self._factor_converter.occupation(y, ms.space.size, y.item, context.get_setting('OccupationAdjustmentToPreventExcessHeight') ) for y in ms.get_products()) for ms in context.mounted_spaces)
        initial_score = self._get_initial_score(context)

        # build helper side options
        helper_side_options: List[List[SafeSideCombinationDto]] = []
        for space in spaces:
            if not space.IsHelperSide():
                continue
            choices = []
            for mounted in mounted_spaces_id:
                if sum(self._factor_converter.occupation(z, space.size, z.item, context.get_setting('OccupationAdjustmentToPreventExcessHeight') ) for z in mounted.MountedSpace.GetProducts()) <= space.size:
                    choices.append(SafeSideCombinationDto(Space=space, MountedSpace=mounted.MountedSpace, MountedSpaceId=mounted.MountedSpaceId, SafeHelperOccupation=sum(self._factor_converter.occupation(z.GetSideQuantity('Helper'), space.size, z.item, context.get_setting('OccupationAdjustmentToPreventExcessHeight') ) for z in mounted.MountedSpace.GetProducts()), IndifferentOccupation=sum(self._factor_converter.occupation(z.GetSideQuantity('Indifferent'), space.size, z.item, context.get_setting('OccupationAdjustmentToPreventExcessHeight') ) for z in mounted.MountedSpace.GetProducts())))
            helper_side_options.append(choices)

        helper_combination = self._get_helper_side_combination(context, max(s.number for s in spaces), initial_score, helper_side_options, mounted_spaces_id)
        if not helper_combination:
            context.add_execution_log(f'Mapa {context.MapNumber}, Nenhuma combinacao melhor encontrada, finalizando execucao da regra.')
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
                if sum(self._factor_converter.occupation(z, space.size, z.item, context.get_setting('OccupationAdjustmentToPreventExcessHeight') ) for z in mounted.MountedSpace.GetProducts()) <= space.size:
                    choices.append(SafeSideCombinationDto(Space=space, MountedSpace=mounted.MountedSpace, MountedSpaceId=mounted.MountedSpaceId))
            drive_side_options.append(choices)

        driver_combination = self._get_driver_side_combination(context, max(s.number for s in spaces), drive_side_options)
        if not driver_combination:
            context.add_execution_log(f'Mapa {context.MapNumber}, Nao foi possivel achar uma opcao para o lado motorista, finalizando execucao da regra.')
            return context

        # Apply changes
        for item in helper_combination:
            item.MountedSpace.SetSpace(item.space)
        for item in driver_combination:
            item.MountedSpace.SetSpace(item.space)

        # Recompute score and finish
        self._get_final_score(context)
        context.add_execution_log('Finalizado a execucao da regra')
        return context

    # ---------------- helper methods ---------------------------------
    def _seed_delivery_order_amount(self, context: Context) -> None:
        # mirrors C#: populate delivery order quantities and log
        complex_delivery_order = context.GetComplexDeliveryOrder()

        indifferent = context.GetDeliveriesIndifferentSafeSide()
        self._log_delivery_orders(context, indifferent, TruckSafeSide.INDIFFERENT)

        helper = context.GetDeliveriesHelperSafeSide()
        self._log_delivery_orders(context, helper, TruckSafeSide.HELPER)

        driver = context.GetDeliveriesDriverSafeSide()
        self._log_delivery_orders(context, driver, TruckSafeSide.DRIVER)

        # seed per side
        self._seed_delivery_order_amount_per_side(context, TruckBaySide.HELPER, complex_delivery_order, indifferent, helper, driver)
        self._seed_delivery_order_amount_per_side(context, TruckBaySide.DRIVER, complex_delivery_order, indifferent, helper, driver)

    def _log_delivery_orders(self, context: Context, deliveries: Iterable[int], safe_side: str) -> None:
        s = ', '.join(str(d) for d in deliveries)
        context.add_execution_log(f'Safe Side: {safe_side} - Deliveries: {s}')

    def _seed_delivery_order_amount_per_side(self, context: Context, truck_side: str, complex_delivery_order: int, indifferent_deliveries: Iterable[int], helper_deliveries: Iterable[int], driver_deliveries: Iterable[int]) -> None:
        # Iterate mounted products by side and distribute amounts by delivery order as C# does
        mounted_products = []
        for ms in context.mounted_spaces:
            if getattr(ms.space, 'Side', '').lower() == truck_side.lower():
                mounted_products.extend(ms.get_products())

        # assume mounted_products already ordered and have AddDeliveryOrderQuantity
        for mp in mounted_products:
            total_amount = mp.Amount
            item = mp.item
            for delivery_order in sorted(item.DeliveryOrdersWithAmount(), key=lambda x: (x == complex_delivery_order, truck_side == 'Helper' and x in helper_deliveries, x in indifferent_deliveries), reverse=True):
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
        helper_safe = sum(self._factor_converter.occupation(z.GetSideQuantity('Helper'), y.space.size, z.item, context.get_setting('OccupationAdjustmentToPreventExcessHeight') ) for y in context.mounted_spaces for z in y.get_products().WithAmount())
        driver_safe = sum(self._factor_converter.occupation(z.GetSideQuantity('Driver'), y.space.size, z.item, context.get_setting('OccupationAdjustmentToPreventExcessHeight') ) for y in context.mounted_spaces for z in y.get_products().WithAmount())
        indifferent = sum(self._factor_converter.occupation(z.GetSideQuantity('Indifferent'), y.space.size, z.item, context.get_setting('OccupationAdjustmentToPreventExcessHeight') ) for y in context.mounted_spaces for z in y.get_products().WithAmount())

        total_safe = helper_safe + driver_safe + indifferent
        score = (total_safe / self.TotalOccupation) if self.TotalOccupation != 0 else 0
        context.add_execution_log(f'Mapa {context.MapNumber} - Score {score_log_text}({score:.2f})Pts; Ocupacao Segura({total_safe:.2f}); Ocupacao Total({self.TotalOccupation:.2f}).')
        return score

    def _get_helper_side_combination(self, context: Context, max_bay_number: int, initial_score: float, helper_side_options: List[List[SafeSideCombinationDto]], mounted_spaces_id: List[MountedSpaceIdDto]) -> Optional[List[SafeSideCombinationDto]]:
        # produce cartesian product combinations where no mountedSpaceId is repeated
        all_combinations = list(itertools.product(*helper_side_options)) if helper_side_options else [[]]
        valid = []
        for combo in all_combinations:
            ids = [c.MountedSpaceId for c in combo]
            if len(ids) != len(set(ids)):
                continue
            valid.append(list(combo))

        # filter valid combinations by load balance and chopp position (simplified: keep as-is)
        best = None
        best_score = initial_score
        for combo in valid:
            score_val = (sum(c.SafeHelperOccupation + c.IndifferentOccupation for c in combo) + sum(m.SafeDriverCurrentOccupation + m.IndifferentOccupation for m in mounted_spaces_id if m.MountedSpace not in [c.MountedSpace for c in combo])) / (self.TotalOccupation or 1)
            if score_val > best_score:
                best_score = score_val
                best = combo

        return best

    def _get_driver_side_combination(self, context: Context, max_bay_number: int, drive_side_options: List[List[SafeSideCombinationDto]]) -> Optional[List[SafeSideCombinationDto]]:
        all_combinations = list(itertools.product(*drive_side_options)) if drive_side_options else [[]]
        for combo in all_combinations:
            ids = [c.MountedSpaceId for c in combo]
            if len(ids) != len(set(ids)):
                continue
            return list(combo)
        return None
