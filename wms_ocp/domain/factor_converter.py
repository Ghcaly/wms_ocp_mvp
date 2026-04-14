from decimal import Decimal, getcontext, ROUND_DOWN, ROUND_HALF_EVEN
import math
from typing import Any, Optional
from ..domain.space import Space
from multipledispatch import dispatch
from ..domain.mounted_product import MountedProduct
from ..domain.pallet_setting import PalletSetting
from ..domain.space_size import SpaceSize
from ..domain.item import Item
from ..domain.factor import Factor
from ..domain.mounted_space import MountedSpace

class FactorConverter:
    """A minimal port of the C# FactorConverter used by the rules.

    This implementation is defensive: it tries to read product/factor/pallet_setting
    attributes on the Python domain objects when present and falls back to safe
    defaults when attributes are missing. The goal is behavioral parity for
    occupation/quantity calculations used by rules.
    """

    def __init__(self) -> None:
        # decimal context can be tuned if needed
        # getcontext().prec = 12 
        getcontext().prec = 28
        getcontext().rounding = ROUND_HALF_EVEN

    def _to_decimal(self, value: Any) -> Decimal:
        try:
            if isinstance(value, float):
                return Decimal(str(value))
            return Decimal(value)
        except Exception:
            try:
                return Decimal(str(value))
            except Exception:
                return Decimal(0)
            
    # def _to_decimal(self, value: Any) -> Decimal:
    #     try:
    #         return Decimal(value)
    #     except Exception:
    #         try:
    #             return Decimal(str(value))
    #         except Exception:
    #             return Decimal(0)

    def _factor_value(self, factor_or_space_size: Any, item: Any = None) -> Decimal:
        # factor may be an object with .value, a numeric, or a space_size enum
        if factor_or_space_size is None:
            return Decimal(1)
        # If the caller passed a factor-like object with 'value'
        val = None
        if hasattr(factor_or_space_size, 'value'):
            val = getattr(factor_or_space_size, 'value')
        elif isinstance(factor_or_space_size, (int, float, Decimal)):
            val = factor_or_space_size
        # If factor_or_space_size seems like a space size (int) and item has product.get_factor
        elif item is not None and hasattr(item, 'product') and hasattr(item.product, 'get_factor'):
            try:
                f = item.product.get_factor(factor_or_space_size)
                if hasattr(f, 'value'):
                    val = getattr(f, 'value')
                else:
                    val = f
            except Exception:
                val = 1

        return self._to_decimal(val if val is not None else 1)

    def _pallet_setting_values(self, pallet_setting: Any):
        # pallet_setting can be a dict or an object with attributes
        q = None
        qdozen = None
        try:
            if isinstance(pallet_setting, dict):
                q = pallet_setting.get('quantity')
                qdozen = pallet_setting.get('quantity_dozen') or pallet_setting.get('quantityDozen')
            else:
                q = getattr(pallet_setting, 'quantity', None)
                qdozen = getattr(pallet_setting, 'QuantityDozen', None) or getattr(pallet_setting, 'quantityDozen', None)
        except Exception:
            q = None
            qdozen = None

        return int(q) if q not in (None, 0) else None, int(qdozen) if qdozen not in (None, 0) else None

    def _occupation_impl(self, quantity: Any, factor: Any = None, pallet_setting: Any = None, item: Any = None, calculate_additional: bool = False, decimal_places: int = 2) -> Decimal:
        """Core occupation calculation, ported from C# FactorConverter.Occupation.

        Dispatcher overloads should normalize parameters and call this method.
        """
        qty = self._to_decimal(quantity)
        additional = self._set_additional_occupation(qty, item, calculate_additional)

        # compute base occupation following C#: adjust quantity if palletSetting.Quantity != QuantityDozen
        q = pallet_setting.Quantity 
        qdozen = pallet_setting.QuantityDozen

        if q is not None and qdozen is not None and q != qdozen:
            denom = q if q != 0 else 1
            qty = qty * Decimal(qdozen) / Decimal(denom)

        factor_value = self._factor_value(factor, item)
        #temporario 17_12_2025
        precision = int(math.pow(10, decimal_places))

        occupation = qty * (factor_value if factor_value != 0 else Decimal(1)) / Decimal(2)
        truncated = (math.trunc(precision * float(occupation)) / precision) if precision != 0 else occupation

        return self._to_decimal(truncated) + additional
        #temporario 17_12_2025
        # precision = Decimal(10) ** decimal_places
        # occupation = qty * (factor_value if factor_value != 0 else Decimal(1)) / Decimal(2)
        # truncated = (occupation * precision).to_integral_value(rounding=ROUND_DOWN) / precision
        # return truncated + additional

    def unitary_occupation(self, item: Any, factor: Any, pallet_setting: Any) -> Decimal:
        """Occupation for a single unit (C# UnitaryOccupation)."""
        additional = self._get_unitary_item_additional_occupation(item)
        occ = self._occupation_static(1, factor, pallet_setting, decimal_places=4)
        return occ + additional

    def _occupation_static(self, quantity: Any, factor: Any, pallet_setting: Any, decimal_places: int = 2) -> Decimal:
        # small helper used by unitary_occupation and internal calculations
        qty = self._to_decimal(quantity)
        q, qdozen = self._pallet_setting_values(pallet_setting)
        if q is not None and qdozen is not None and q != qdozen:
            denom = q if q != 0 else 1
            qty = qty * Decimal(qdozen) / Decimal(denom)

        factor_value = self._factor_value(factor)
        #temporario 17_12_2025
        # precision = int(math.pow(10, decimal_places))
        # occupation = qty * (factor_value if factor_value != 0 else Decimal(1)) / Decimal(2)
        # truncated = (math.trunc(precision * float(occupation)) / precision) if precision != 0 else occupation
        # return self._to_decimal(truncated)
        # temporario 17_12_2025
        precision = Decimal(10) ** decimal_places
        occupation = qty * (factor_value if factor_value != 0 else Decimal(1)) / Decimal(2)
        truncated = (occupation * precision).to_integral_value(rounding=ROUND_DOWN) / precision

        return truncated

        # precision = int(math.pow(10, decimal_places))

        # occupation = qty * (factor_value if factor_value != 0 else Decimal(1)) / Decimal(2)
        # truncated = (math.trunc(precision * float(occupation)) / precision) if precision != 0 else occupation

        # return self._to_decimal(truncated)

    def quantity(self, quantity: Any, factor: Any, pallet_setting: Any) -> Decimal:
        """Inverse of occupation: convert occupation-based value to quantity (C# Quantity)."""
        # Implemented exactly like the C# method (no defensive checks)
        q = Decimal(quantity)
        result = q / (Decimal(factor.Value) if factor.Value != 0 else Decimal(1)) * Decimal(2)

        if pallet_setting.Quantity != pallet_setting.QuantityDozen:
            settingQuantity = (pallet_setting.Quantity if pallet_setting.Quantity != 0 else 1)
            denom = (pallet_setting.QuantityDozen / settingQuantity)
            if denom == 0:
                denom = 1
            result = result / Decimal(denom)

        return result

    def quantity_per_factor(self, space: Any, quantity: int, factor: Any, item: Any, calculate_additional: bool) -> Decimal:
        """Equivalent to C# QuantityPerFactor: how many units fit given the factor and space.

        If occupation(quantity) <= space -> return quantity.
        Otherwise, try to compute using additional occupation unitary; fallback to quantity(space)
        """
        space_dec = self._to_decimal(space)
        occ = self.occupation(quantity, factor, item.Product.PalletSetting, item, calculate_additional)

        if occ <= space_dec:
            return self._to_decimal(quantity)
        
        quantityWithAdditional = self.GetQuantityToRemainingSpaceWithAdditional(space, factor, item, calculate_additional, item.Product.PalletSetting, quantity)

        if quantityWithAdditional is not None:
            return quantityWithAdditional
        
        return self.quantity(space_dec, factor, item.Product.PalletSetting)
    
    #temporario
    def quantity_per_factor_old(self, space: Any, quantity: int, factor: Any, item: Any, calculate_additional: bool) -> Decimal:
        """Equivalent to C# QuantityPerFactor: how many units fit given the factor and space.

        If occupation(quantity) <= space -> return quantity.
        Otherwise, try to compute using additional occupation unitary; fallback to quantity(space)
        """
        space_dec = self._to_decimal(space)
        occ = self.occupation(quantity, factor, item.Product.PalletSetting, item, calculate_additional)

        if occ <= space_dec:
            return self._to_decimal(quantity)

        # try quantity with additional occupation
        unitary = self.unitary_occupation(item, factor, item.Product.PalletSetting)
        try:
            if unitary == 0:
                return self.quantity(space_dec, factor, item.Product.PalletSetting)
            quantity_to_space_remaining = math.floor(float(space_dec / unitary))
            if quantity_to_space_remaining < quantity:
                return Decimal(quantity_to_space_remaining)
        except Exception:
            pass

        return self.quantity(space_dec, factor, item.Product.PalletSetting)

    def GetQuantityToRemainingSpaceWithAdditional(self, space: Any, factor: Any, item: Any, calculate_additional_occupation: bool, settings: Any, quantity: int):
        """Port of C# GetQuantityToRemainingSpaceWithAdditional.

        Returns a Decimal with the quantity that fits considering additional
        occupation, or `None` when additional occupation is not applicable.
        """
        try:
            if not calculate_additional_occupation:
                return None
            prod = getattr(item, 'Product', getattr(item, 'product', None))
            if prod is None or not getattr(prod, 'CalculateAdditionalOccupation', getattr(prod, 'calculate_additional_occupation', False)):
                return None

            # resolve pallet setting to pass to unitary occupation
            pallet_setting = None
            try:
                pallet_setting = getattr(prod, 'PalletSetting', getattr(prod, 'pallet_setting', None))
            except Exception:
                pallet_setting = None

            unitary_occupation = self.unitary_occupation(item, factor, pallet_setting)
            if not unitary_occupation or float(unitary_occupation) == 0.0:
                return None

            # compute how many units fit by floor(space / unitaryOccupation)
            try:
                # temporario 17_12_2025
                # qty_fit = math.floor(float(Decimal(space) / Decimal(unitary_occupation)))
                qty_fit = int(Decimal(space) // Decimal(unitary_occupation))
            except Exception:
                try:
                    qty_fit = math.floor(float(space) / float(unitary_occupation))
                except Exception:
                    return None

            return Decimal(qty_fit) if qty_fit < quantity else Decimal(quantity)
        except Exception:
            return None

    # --- QuantityToRemainingSpace overloads (faithful to C# signatures) ---
    @dispatch(MountedSpace, Item, object)
    def quantity_to_remaining_space(self, mounted_space: MountedSpace, item: Item, settings: Any) -> Decimal:
        """QuantityToRemainingSpace(IMountedSpace mountedSpace, IItem item, ISetting settings)

        Implements: return QuantityToRemainingSpace(mountedSpace.Space.Size, mountedSpace.OccupationRemaining, item, settings)
        """
        try:
            space_size = getattr(getattr(mounted_space, 'Space', getattr(mounted_space, 'space', None)), 'Size', getattr(getattr(mounted_space, 'Space', getattr(mounted_space, 'space', None)), 'size', None))
        except Exception:
            space_size = getattr(getattr(mounted_space, 'space', None), 'size', None)

        try:
            occupation_remaining = getattr(mounted_space, 'OccupationRemaining', getattr(mounted_space, 'occupation_remaining', getattr(mounted_space, 'occupation', None)))
        except Exception:
            occupation_remaining = getattr(mounted_space, 'occupation_remaining', getattr(mounted_space, 'occupation', None))

        return self.quantity_to_remaining_space(space_size, occupation_remaining, item, settings)

    @dispatch(Decimal, Decimal, Item, object)
    def quantity_to_remaining_space(self, space_size: Decimal, occupation_remaining: Decimal, item: Item, settings: Any) -> Decimal:
        """QuantityToRemainingSpace(SpaceSize size, decimal occupationRemaining, IItem item, ISetting settings)"""
        # resolve factor from item/product
        factor = None
        prod = getattr(item, 'Product', getattr(item, 'product', None))
        try:
            if prod is not None and hasattr(prod, 'GetFactor'):
                factor = getattr(prod, 'GetFactor', getattr(prod, 'get_factor'))(space_size)
        except Exception:
            factor = None

        calculate_additional = False
        try:
            calculate_additional = getattr(settings, 'OccupationAdjustmentToPreventExcessHeight', getattr(settings, 'get', lambda k, d: d)('OccupationAdjustmentToPreventExcessHeight', False))
        except Exception:
            calculate_additional = False

        return self.quantity_per_factor(occupation_remaining if occupation_remaining is not None else Decimal(0), getattr(item, 'AmountRemaining', getattr(item, 'amount_remaining', getattr(item, 'amount', 0))), factor, item, calculate_additional)


    @dispatch(SpaceSize, Decimal, Item, object)
    def quantity_to_remaining_space(self, space_size: SpaceSize, occupation_remaining: Decimal, item: Item, settings: Any) -> Decimal:
        """QuantityToRemainingSpace(SpaceSize size, decimal occupationRemaining, IItem item, ISetting settings)"""
        # resolve factor from item/product
        factor = None
        prod = getattr(item, 'Product', getattr(item, 'product', None))
        try:
            if prod is not None and hasattr(prod, 'GetFactor'):
                factor = getattr(prod, 'GetFactor', getattr(prod, 'get_factor'))(space_size)
        except Exception:
            factor = None

        calculate_additional = False
        try:
            calculate_additional = getattr(settings, 'OccupationAdjustmentToPreventExcessHeight', getattr(settings, 'get', lambda k, d: d)('OccupationAdjustmentToPreventExcessHeight', False))
        except Exception:
            calculate_additional = False

        return self.quantity_per_factor(occupation_remaining if occupation_remaining is not None else Decimal(0), getattr(item, 'AmountRemaining', getattr(item, 'amount_remaining', getattr(item, 'amount', 0))), factor, item, calculate_additional)

    @dispatch(Space, Decimal, Item, object)
    def quantity_to_remaining_space(self, space: Space, occupation_remaining: Decimal, item: Item, settings: Any) -> Decimal:
        """QuantityToRemainingSpace(SpaceSize size, decimal occupationRemaining, IItem item, ISetting settings)"""
        # resolve factor from item/product
        factor = None
        prod = getattr(item, 'Product', getattr(item, 'product', None))
        try:
            if prod is not None and hasattr(prod, 'GetFactor'):
                factor = getattr(prod, 'GetFactor', getattr(prod, 'get_factor'))(space.Size)
        except Exception:
            factor = None

        calculate_additional = False
        try:
            calculate_additional = getattr(settings, 'OccupationAdjustmentToPreventExcessHeight', getattr(settings, 'get', lambda k, d: d)('OccupationAdjustmentToPreventExcessHeight', False))
        except Exception:
            calculate_additional = False

        return self.quantity_per_factor(occupation_remaining if occupation_remaining is not None else Decimal(0), getattr(item, 'AmountRemaining', getattr(item, 'amount_remaining', getattr(item, 'amount', 0))), factor, item, calculate_additional)


    @dispatch(MountedSpace, Item, int, object)
    def quantity_to_remaining_space(self, mounted_space: MountedSpace, item: Item, quantity: int, settings: Any) -> Decimal:
        """QuantityToRemainingSpace(IMountedSpace mountedSpace, IItem item, int quantity, ISetting settings)"""
        try:
            space_size = getattr(getattr(mounted_space, 'Space', getattr(mounted_space, 'space', None)), 'Size', getattr(getattr(mounted_space, 'Space', getattr(mounted_space, 'space', None)), 'size', None))
        except Exception:
            space_size = getattr(getattr(mounted_space, 'space', None), 'size', None)

        try:
            occupation_remaining = getattr(mounted_space, 'OccupationRemaining', getattr(mounted_space, 'occupation_remaining', getattr(mounted_space, 'occupation', None)))
        except Exception:
            occupation_remaining = getattr(mounted_space, 'occupation_remaining', getattr(mounted_space, 'occupation', None))

        prod = getattr(item, 'Product', getattr(item, 'product', None))
        try:
            factor = getattr(prod, 'GetFactor', getattr(prod, 'get_factor'))(space_size) if prod is not None else None
        except Exception:
            factor = None

        return self.quantity_per_factor(occupation_remaining if occupation_remaining is not None else Decimal(0), int(quantity), factor, item, getattr(settings, 'OccupationAdjustmentToPreventExcessHeight', False) if settings else False)

    @dispatch(object, MountedSpace, Item, int)
    def quantity_to_remaining_space(self, context: object, mounted_space: MountedSpace, item: Item, quantity: int) -> Decimal:
        """QuantityToRemainingSpace(IRuleContext context, IMountedSpace mountedSpace, IItem item, int quantity)"""
        try:
            space_size = getattr(getattr(mounted_space, 'Space', getattr(mounted_space, 'space', None)), 'Size', getattr(getattr(mounted_space, 'Space', getattr(mounted_space, 'space', None)), 'size', None))
        except Exception:
            space_size = getattr(getattr(mounted_space, 'space', None), 'size', None)

        # use occupation remaining with potential volume reduction logic
        try:
            occupation_remaining = self.get_occupation_remaining_with_volume_reduction(context, mounted_space, item)
        except Exception:
            occupation_remaining = getattr(mounted_space, 'OccupationRemaining', getattr(mounted_space, 'occupation_remaining', getattr(mounted_space, 'occupation', None)))

        prod = getattr(item, 'Product', getattr(item, 'product', None))
        try:
            factor = getattr(prod, 'GetFactor', getattr(prod, 'get_factor'))(space_size) if prod is not None else None
        except Exception:
            factor = None

        calculate_additional = False
        try:
            calculate_additional = context.get_setting('OccupationAdjustmentToPreventExcessHeight', False)
        except Exception:
            calculate_additional = getattr(context, 'settings', {}).get('OccupationAdjustmentToPreventExcessHeight', False)

        return self.quantity_per_factor(occupation_remaining if occupation_remaining is not None else Decimal(0), int(quantity), factor, item, calculate_additional)

    # Fallback generic signature to preserve older non-dispatched callers
    # @dispatch(object, object, object, object)
    # def quantity_to_remaining_space(self, a, b, c, d) -> Decimal:
    #     # delegate to earlier generic implementation semantics
    #     try:
    #         # try mounted_space variant
    #         if hasattr(a, 'GetProducts') or hasattr(a, 'GetContainers') or hasattr(a, 'Space'):
    #             return self.quantity_to_remaining_space(a, b, c)
    #     except Exception:
    #         pass
    #     # best-effort: compute using the generic quantity_per_factor
    #     try:
    #         return self.quantity_per_factor(Decimal(a), int(b), c, d, False)
    #     except Exception as e:
    #         print(f"Error in generic quantity_to_remaining_space: {e}")
    #         return Decimal(0)

    def get_occupation_remaining_with_volume_reduction(self, context: Any, mounted_space: Any, item: Any = None) -> Decimal:
        """If ReduceVolumePallets setting is enabled, compute reduced occupation remaining.

        This is a simplified port of the C# logic that uses packing group codes. The Python port
        attempts to mimic the reduction formula if settings are present; otherwise returns
        mounted_space.occupation_remaining (or mounted_space.occupation) when available.
        """
        occupation_remaining = getattr(mounted_space, 'occupation_remaining', getattr(mounted_space, 'occupation', None))
        if occupation_remaining is None:
            # fallback: if mounted_space.space has size and no occupation, return its size
            occupation_remaining = getattr(getattr(mounted_space, 'space', None), 'size', Decimal(0))

        reduce_flag = False
        try:
            reduce_flag = bool(context.get_setting('ReduceVolumePallets', False))
        except Exception:
            try:
                reduce_flag = bool(getattr(context, 'settings', {}).get('ReduceVolumePallets', False))
            except Exception:
                reduce_flag = False

        if not reduce_flag:
            return self._to_decimal(occupation_remaining)

        percentage = getattr(context, 'settings', {}).get('PercentageReductionInPalletOccupancy', 0) if hasattr(context, 'settings') else context.get_setting('PercentageReductionInPalletOccupancy', 0) if hasattr(context, 'get_setting') else 0
        try:
            percentage = float(percentage)
        except Exception:
            percentage = 0

        space_size = getattr(getattr(mounted_space, 'space', None), 'size', None)
        if space_size is None:
            return self._to_decimal(occupation_remaining)

        mounted_space_size_reduced = float(space_size) - ((percentage / 100.0) * float(space_size))
        occupation_remaining_reduced = mounted_space_size_reduced - float(getattr(mounted_space, 'occupation', 0))
        if occupation_remaining_reduced < 0:
            return Decimal(0)
        return Decimal(occupation_remaining_reduced)

    def _set_additional_occupation(self, quantity: Decimal, item: Any, calculate_additional: bool) -> Decimal:
        
        item.set_additional_occupation(0)
        additional = self._get_additional_occupation(quantity, item, calculate_additional)
        # if item exposes set_additional_occupation, call it
        try:
            if hasattr(item, 'set_additional_occupation'):
                item.set_additional_occupation(additional)
        except Exception:
            pass
        return additional

    def _get_additional_occupation(self, quantity: Decimal, item: Any, calculate_additional: bool) -> Decimal:
        if not calculate_additional:
            return Decimal(0)
        if item is None:
            return Decimal(0)
        product = getattr(item, 'product', None)
        if product is None:
            return Decimal(0)
        if not getattr(product, 'calculate_additional_occupation', False):
            return Decimal(0)

        unit = self._get_unitary_item_additional_occupation(item)
        try:
            return Decimal(unit) * Decimal(quantity)
        except Exception:
            return Decimal(0)

    def _get_unitary_item_additional_occupation(self, item: Any, decimal_places: int = 2) -> Decimal:
        # Port of GetUnitaryItemAdditionalOccupation
        product = getattr(item, 'product', None)
        if product is None:
            return Decimal(0)
        ballast_qty = getattr(product, 'ballast_quantity', getattr(product, 'ballastQuantity', 0))
        if not ballast_qty or ballast_qty <= 0:
            return Decimal(0)

        total_area_ballast = getattr(product, 'total_area_occupied_by_ballast', getattr(product, 'totalAreaOccupiedByBallast', None))
        total_area_unit = getattr(product, 'total_area_occupied_by_unit', getattr(product, 'totalAreaOccupiedByUnit', None))
        if total_area_ballast is None or total_area_unit is None:
            return Decimal(0)

        # comparator constant from C# CalculatorConstants.ComparatorItemTotalAreaOccupiedByBallast = 35.01 * 51.20 * 7
        from .calculator_constants import CalculatorConstants
        comparator = float(CalculatorConstants.ComparatorItemTotalAreaOccupiedByBallast)

        try:
            diff = (comparator - float(total_area_ballast)) / float(ballast_qty)
            diff = abs(diff)
            precision = int(math.pow(10, decimal_places))
            additional = math.floor(precision * (diff / float(total_area_unit))) / precision
            return Decimal(additional)
        except Exception:
            return Decimal(0)

    # --- PascalCase aliases for C# compatibility ---
    # Occupation = occupation
    UnitaryOccupation = unitary_occupation
    Quantity = quantity
    QuantityPerFactor = quantity_per_factor
    QuantityToRemainingSpace = quantity_to_remaining_space
    GetOccupationRemainingWithVolumeReduction = get_occupation_remaining_with_volume_reduction
    # Additional occupation helpers
    SetAdditionalOccupation = _set_additional_occupation
    GetAdditionalOccupation = _get_additional_occupation
    GetUnitaryItemAdditionalOccupation = _get_unitary_item_additional_occupation

    # # snake_case aliases (if code expects them)
    # occupation = occupation
    # unitary_occupation = unitary_occupation
    # quantity = quantity
    # quantity_per_factor = quantity_per_factor
    # quantity_to_remaining_space = quantity_to_remaining_space
    # get_occupation_remaining_with_volume_reduction = get_occupation_remaining_with_volume_reduction


# --- multipledispatch-based Occupation overloads bound to FactorConverter ---
    @dispatch(int, Decimal, Item, bool)
    def occupation(self, quantity: int, space_size: Decimal, item: Item, calculate_additional: bool) -> Decimal:
        # prod = getattr(item, 'Product', getattr(item, 'product', None))
        # try:
        #     factor = getattr(prod, 'GetFactor', getattr(prod, 'get_factor'))(space_size)
        # except Exception:
        #     factor = None

        # pallet_setting = getattr(prod, 'PalletSetting', getattr(prod, 'pallet_setting', None))
        return self._occupation_impl(quantity, item.Product.get_factor(space_size), item.Product.PalletSetting, item, calculate_additional)

    @dispatch(MountedProduct, int, Item, bool)
    def occupation(self, mounted_product: MountedProduct, space_size: int, item: Item, calculate_additional: bool) -> Decimal:
        # duck-typed IMountedProduct
        if hasattr(mounted_product, 'Amount') and hasattr(mounted_product, 'Product'):
            try:
                factor = getattr(mounted_product.Product, 'GetFactor', getattr(mounted_product.Product, 'get_factor'))(Decimal(space_size))
            except Exception:
                factor = None
            pallet_setting = getattr(mounted_product.Product, 'PalletSetting', getattr(mounted_product.Product, 'pallet_setting', None))
            amount = getattr(mounted_product, 'Amount', getattr(mounted_product, 'amount', 0))
            return self._occupation_impl(amount, factor, pallet_setting, item, calculate_additional)
        # fallback: try to coerce
        raise TypeError('Unsupported IMountedProduct shape for occupation')
    
    @dispatch(MountedProduct, Decimal, Item, bool)
    def occupation(self, mounted_product: MountedProduct, space_size: Decimal, item: Item, calculate_additional: bool) -> Decimal:
        # duck-typed IMountedProduct
        if hasattr(mounted_product, 'Amount') and hasattr(mounted_product, 'Product'):
            try:
                factor = getattr(mounted_product.Product, 'GetFactor', getattr(mounted_product.Product, 'get_factor'))(space_size)
            except Exception:
                factor = None
            pallet_setting = getattr(mounted_product.Product, 'PalletSetting', getattr(mounted_product.Product, 'pallet_setting', None))
            amount = getattr(mounted_product, 'Amount', getattr(mounted_product, 'amount', 0))
            return self._occupation_impl(amount, factor, pallet_setting, item, calculate_additional)
        # fallback: try to coerce
        raise TypeError('Unsupported IMountedProduct shape for occupation')


    @dispatch(Decimal, Factor, Item, bool)
    def occupation(self, quantity: Decimal, factor: Factor, item: Item, calculate_additional: bool) -> Decimal:
        pallet_setting = getattr(item, 'Product', getattr(item, 'product', None))
        pallet_setting = getattr(pallet_setting, 'PalletSetting', getattr(pallet_setting, 'pallet_setting', None))
        return self._occupation_impl(quantity, factor, pallet_setting, item, calculate_additional)

    @dispatch(int, Factor, Item, bool)
    def occupation(self, quantity: int, factor: Factor, item: Item, calculate_additional: bool) -> Decimal:
        return self._occupation_impl(quantity, factor, item.Product.PalletSetting, item, calculate_additional)

    @dispatch(int, Factor, PalletSetting, Item, bool)
    def occupation(self, quantity: int, factor: Factor, pallet_setting: PalletSetting, item: Item, calculate_additional: bool) -> Decimal:
        return self._occupation_impl(quantity, factor, pallet_setting, item, calculate_additional)
    
    def Occupation(self, *args, **kwargs):
        return self.occupation(*args, **kwargs)
