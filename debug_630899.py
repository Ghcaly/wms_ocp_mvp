"""
Debug script to trace palletization of map 630899 step by step.
Patches key rules to log bay state after execution.
"""
import sys
import os
sys.path.insert(0, '.')

from pathlib import Path
from wms_ocp.adapters.logger_instance import set_logger
from wms_ocp.adapters.logger_system import JsonStepLogger


def bay_state(context, label=""):
    """Print current bay state."""
    ms_list = context.MountedSpaces
    print(f"\n{'='*60}")
    print(f"BAY STATE: {label}")
    print(f"{'='*60}")

    from wms_ocp.domain.mounted_space_list import MountedSpaceList
    msl = MountedSpaceList(ms_list)
    driver = sum(x.Weight for x in msl.DriverSide())
    helper = sum(x.Weight for x in msl.HelperSide())
    total = driver + helper
    print(f"Driver: {driver:.2f} kg ({driver*100/total:.2f}%)" if total else "Driver: 0 kg")
    print(f"Helper: {helper:.2f} kg ({helper*100/total:.2f}%)" if total else "Helper: 0 kg")
    print()

    # Sort by (number, is_driver_side)
    try:
        sorted_ms = sorted(ms_list, key=lambda ms: (ms.Space.Number, ms.Space.IsDriverSide()))
    except Exception:
        sorted_ms = ms_list

    for ms in sorted_ms:
        sp = ms.Space
        side = "Driver" if sp.IsDriverSide() else "Helper"
        num = sp.Number
        occ = ms.Occupation
        weight = ms.Weight

        # Get products
        products = []
        try:
            for mp in ms.GetProducts():
                code = getattr(mp.Product, 'Code', '?')
                qty = getattr(mp, 'Amount', '?')
                grp = getattr(getattr(mp.Product, 'PackingGroup', None), 'GroupCode', '?')
                products.append(f"{code}({qty},g{grp})")
        except Exception as e:
            products = [f"ERROR:{e}"]

        prod_str = ", ".join(products)
        print(f"  {num}/{side}: occ={occ:.2f}, wt={weight:.2f} | {prod_str}")

    # Empty spaces
    try:
        spaces = context.Spaces
        space_labels = ["{}/{}".format(s.Number, "Driver" if s.IsDriverSide() else "Helper") for s in spaces]
        print(f"  Empty spaces available: {space_labels}")
    except Exception:
        pass

    # Not palletized items
    try:
        remaining = [it for it in context.GetItems() if it.HasAmountRemaining()]
        if remaining:
            by_group = {}
            for it in remaining:
                g = getattr(getattr(it.Product, 'PackingGroup', None), 'GroupCode', '?')
                code = it.Code
                amt = it.AmountRemaining
                key = f"g{g}/{code}"
                by_group[key] = by_group.get(key, 0) + amt
            print(f"  Items remaining: {dict(list(by_group.items())[:10])}")
    except Exception as e:
        print(f"  Items remaining: ERROR {e}")
    print()


# Monkey-patch rules to capture state
original_execute_methods = {}

def make_patched_execute(rule_class, original_exec):
    def patched(self, context, *args, **kwargs):
        result = original_exec(self, context, *args, **kwargs)
        bay_state(context, f"After {rule_class.__name__}")
        return result
    return patched


def patch_rules():
    """Patch key rules to log state after execution."""
    # (module_path, ClassName) pairs — explicit to avoid patching wrong imported class
    rules_to_patch = [
        ('wms_ocp.rules.route.bulk_pallet_rule', 'BulkPalletRule'),
        ('wms_ocp.rules.route.pallet_group_subgroup_rule', 'PalletGroupSubGroupRule'),
        ('wms_ocp.rules.route.non_palletized_products_rule', 'NonPalletizedProductsRule'),
        ('wms_ocp.rules.route.isotonic_water_rule', 'IsotonicWaterRule'),
        ('wms_ocp.rules.common.join_mounted_spaces_with_less_occupation_rule', 'JoinMountedSpacesWithLessOccupationRule'),
        ('wms_ocp.rules.common.pallet_equalization_rule', 'PalletEqualizationRule'),
        ('wms_ocp.rules.common.side_balance_rule', 'SideBalanceRule'),
    ]

    import importlib
    for mod_path, class_name in rules_to_patch:
        try:
            mod = importlib.import_module(mod_path)
            obj = getattr(mod, class_name, None)
            if obj is None or not isinstance(obj, type) or not hasattr(obj, 'execute'):
                print(f"Not found: {class_name} in {mod_path}")
                continue
            original = obj.execute
            patched = make_patched_execute(obj, original)
            obj.execute = patched
            print(f"Patched: {class_name}")
        except Exception as e:
            print(f"Failed to patch {mod_path}/{class_name}: {e}")


patch_rules()

# Now run
data_dir = Path('wms_ocp/data')
logger_inst = JsonStepLogger(filepath=str(data_dir / 'trace_log.json'))
set_logger(logger_inst)

xml_path = data_dir / 'xml_in' / '630899.xml'
with open(xml_path, 'rb') as f:
    content = f.read()

from wms_ocp.service.palletizing_processor import PalletizingProcessor
import logging
logging.disable(logging.CRITICAL)  # suppress noise

proc = PalletizingProcessor(debug_enabled=False)
result = proc.run_from_xml(content, filename='630899.xml')
print(f"\nDone: success={result.get('success') if result else None}")
