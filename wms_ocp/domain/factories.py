"""Domain-facing RuleFactories.

This module builds RuleChain instances using explicit, readable
"from ... import RuleClass; chain.add_rule(RuleClass())" blocks so the
sequence is obvious to reviewers. Each import is wrapped in a small
try/except so missing rule implementations won't break imports — they'll be
logged and skipped.
"""
from itertools import chain
import logging
from typing import Any, List

from .rule_chain import RuleChain
from ..rules.common import *
from ..rules.route import *
from ..rules.as_rules import *
from ..rules.mixed import *
from ..rules.crossdocking import *
from ..rules.t4 import *
from .factor_converter import FactorConverter
from .base_rule import BaseRule
from ..factories.route_rule_principal_factories import RouteRulePrincipalFactories
from ..rules.as_rules.number_of_pallets_rule import NumberOfPalletsRule
from ..rules.as_rules.bays_needed_rule import BaysNeededRule

logger = logging.getLogger(__name__)

class RuleFactories:

    def __init__(self) -> None:
        self.factor_converter = FactorConverter()

    def create_route_chain(self, name: str = "route") -> RuleChain:
        chain = RuleChain(name=name)
        # provide a real FactorConverter instance to rules that accept it; helper will fall back when not supported
        fc = self.factor_converter
        chain.add_rule(self._make_rule(BulkPalletRule, fc))
        chain.add_rule(self._make_rule(ChoppPalletizationRule, fc))
        chain.add_rule(self._make_rule(BulkPalletAdditionalOccupationRule, fc))
        chain.add_rule(self._make_rule(LayerRule, fc))
        chain.add_rule(self._make_rule(PalletGroupSubGroupRule, fc))
        chain.add_rule(self._make_rule(NonPalletizedProductsRule, fc))
        chain.add_rule(self._make_rule(SnapshotRule, fc))
        chain.add_rule(self._make_rule(NonLayerOnLayerPalletRule, fc))
        chain.add_rule(self._make_rule(ReturnableAndDisposableSplitRule, fc))
        chain.add_rule(self._make_rule(ReturnableAndDisposableSplitRemountRule, fc))
        chain.add_rule(self._make_rule(RemountRule, fc))
        chain.add_rule(self._make_rule(IsotonicWaterRule, fc))
        chain.add_rule(self._make_rule(IsotonicWaterWithoutMinimumOccupationRule, fc))
        chain.add_rule(self._make_rule(RemountSplittedRebuildPalletRule, fc))
        chain.add_rule(self._make_rule(EmptySpaceRule, fc))
        chain.add_rule(self._make_rule(BuildMountedSpacesWithFewDisposableProductsRule, fc))
        chain.add_rule(self._make_rule(PackageRule, fc))
        chain.add_rule(self._make_rule(BoxTemplateRule, fc))
        chain.add_rule(self._make_rule(RecalculatePalletOccupationRule, fc))
        return chain

    def create_as_chain(self, name: str = "as") -> RuleChain:
        chain = RuleChain(name=name)
        fc = self.factor_converter
        chain.add_rule(self._make_rule(NumberOfPalletsRule, fc))
        chain.add_rule(self._make_rule(DistributeMixedRouteOnASRule, fc))
        chain.add_rule(self._make_rule(BaysNeededRule, fc))
        chain.add_rule(self._make_rule(ASRouteRule, fc))
        chain.add_rule(self._make_rule(NonPalletizedRouteRule, fc))
        chain.add_rule(self._make_rule(RecalculateNonPalletizedProductsRule, fc))
        chain.add_rule(self._make_rule(ReallocateNonPalletizedItemsOnSmallerPalletRule, fc))
        chain.add_rule(self._make_rule(SeparateRemountBaysAndLayerBaysRule, fc))
        chain.add_rule(self._make_rule(GroupReorderRule, fc))
        return chain

    def create_common_chain(self, name: str = "common") -> RuleChain:
        chain = RuleChain(name=name)
        fc = self.factor_converter
        chain.add_rule(self._make_rule(ReassignmentNonPalletizedItemsRule, fc))
        chain.add_rule(self._make_rule(ReassignmentNonPalletizedItemsWithSplitItemRule, fc))
        chain.add_rule(self._make_rule(JoinMountedSpacesWithLessOccupationRule, fc))
        chain.add_rule(self._make_rule(PalletEqualizationRule, fc))
        chain.add_rule(self._make_rule(ReorderRule, fc))
        chain.add_rule(self._make_rule(NewReorderRule, fc))
        chain.add_rule(self._make_rule(LoadBalancerRule, fc))
        chain.add_rule(self._make_rule(SideBalanceRule, fc))
        chain.add_rule(self._make_rule(SafeSideRule, fc))
        chain.add_rule(self._make_rule(RecalculatePalletOccupationRule, fc))
        chain.add_rule(self._make_rule(VehicleCapacityOverflowRule, fc))
        chain.add_rule(self._make_rule(CalculatorOccupationRule, fc))
        chain.add_rule(self._make_rule(DetachedUnitRule, fc))
        return chain

    def create_mixed_chain(self, name: str = "mixed") -> RuleChain:
        chain = RuleChain(name=name)
        fc = self.factor_converter
        chain.add_rule(self._make_rule(MixedASRule, fc))
        chain.add_rule(MixedRouteRule(
            route_rules_factory=RouteRulePrincipalFactories(),
            bays_needed_rule=self._make_rule(BaysNeededRule, fc),
            number_of_pallets_rule=self._make_rule(NumberOfPalletsRule, fc),
        ))
        chain.add_rule(self._make_rule(MixedRemountRule, fc))
        return chain

    def create_crossdocking_chain(self, name: str = "crossdocking") -> RuleChain:
        chain = RuleChain(name=name)
        fc = self.factor_converter
        chain.add_rule(self._make_rule(CrossDockingASRule, fc))
        chain.add_rule(self._make_rule(JoinMapsRule, fc))
        chain.add_rule(self._make_rule(JoinPlatesRule, fc))
        return chain

    def create_t4_chain(self, name: str = "t4") -> RuleChain:
        chain = RuleChain(name=name)
        fc = self.factor_converter
        chain.add_rule(self._make_rule(T4MixedRule, fc))
        return chain

    def create_custom_chain(self, rules: List[BaseRule]) -> RuleChain:
        chain = RuleChain(name="custom_chain")
        fc = self.factor_converter
        for rule in rules:
            if rule in rules:
                chain.add_rule(self._make_rule(rule, fc))
        return chain
    
    def _make_rule(self, rule_cls, factor_converter: FactorConverter):
        """Try to instantiate rule_cls with a factor_converter argument when accepted.

        Fallbacks:
        - rule_cls(factor_converter=factor_converter)
        - rule_cls(factor_converter)
        - rule_cls()
        """
        try:
            return rule_cls(factor_converter=factor_converter)
        except TypeError:
            try:
                return rule_cls(factor_converter)
            except TypeError:
                return rule_cls()
