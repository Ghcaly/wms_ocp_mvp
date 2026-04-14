from .isotonic_water_rule import IsotonicWaterRule
from .non_layer_on_layer_pallet_rule import NonLayerOnLayerPalletRule
from .pallet_group_subgroup_rule import PalletGroupSubGroupRule
from .returnable_and_disposable_split_remount_rule import ReturnableAndDisposableSplitRemountRule
from ...domain.base_rule import BaseRule
from ...domain.itemList import ItemList


class RemountSplittedRebuildPalletRule(BaseRule):
    """Faithful Python port of C# RemountSplittedRebuildPalletRule.
    
    Handles remount optimization by testing if splitting products results in fewer remounts.
    Uses a snapshot to test alternative allocation strategies without affecting original context.
    
    Flow:
    1. Check if snapshot exists and has remounts with splitted products
    2. Run allocation rules on snapshot (non-layer, returnable/disposable, isotonic)
    3. Compare remount counts between original and snapshot
    4. Apply snapshot if it performs better (fewer remounts and non-palletized items)
    """

    def __init__(self, 
                 non_layer_on_layer_rule=None,
                 returnable_and_disposable_split_remount_rule=None,
                 pallet_group_subgroup_rule=None,
                 isotonic_water_rule=None):
        super().__init__()
        self.non_layer_on_layer_rule = non_layer_on_layer_rule or NonLayerOnLayerPalletRule()
        self.returnable_and_disposable_split_remount_rule = returnable_and_disposable_split_remount_rule or ReturnableAndDisposableSplitRemountRule()
        self.pallet_group_subgroup_rule = pallet_group_subgroup_rule or PalletGroupSubGroupRule()
        self.isotonic_water_rule = isotonic_water_rule or IsotonicWaterRule()

    def should_execute(self, context, item_predicate=None, mounted_space_predicate=None):
        """C#: ShouldExecute - verify if snapshot exists, has remounts and has splitted products"""
        snapshot = context.Snapshot
        
        if snapshot is None:
            context.add_execution_log("Snapshot nao existe, pulando regra de remount com rebuild.")
            return False
        
        # Count remount mounted spaces (not chopp)
        remount_quantity = context.MountedSpaces.IsRemount().NotChopp().count()
        
        # Check if any mounted space has splitted products
        has_splitted = context.MountedSpaces.IsSplitted().any()
        
        if not (remount_quantity > 0 and has_splitted):
            context.add_execution_log("Snapshot nao possui produtos divididos, pulando regra de remount com rebuild.")
            return False
        
        return remount_quantity > 0 and has_splitted

    def execute(self, context, item_predicate=None, mounted_space_predicate=None):
        """C#: Execute - test snapshot allocation and apply if better than original"""
        snapshot = context.Snapshot
        
        # Count original metrics
        remount_quantity = context.MountedSpaces.IsRemount().NotChopp().count()
        not_palletized_quantity = ItemList(context.GetItems()).NotMarketplace().WithAmountRemaining().count()
        
        # Step 1: Run non-layer on layer rule if snapshot has layers (all not keg exclusive)
        if snapshot.MountedSpaces.IsLayer().any() and all(ms.NotKegExclusive() for ms in snapshot.MountedSpaces):
            self.non_layer_on_layer_rule.execute(
                snapshot,
                lambda x: x.NotChopp() and x.NotIsotonicWater() and x.HasAmountRemaining(),
                lambda x: x.HasLayer()
            )
        
        # Step 2: Run returnable/disposable split remount rule
        self.returnable_and_disposable_split_remount_rule.execute(
            snapshot,
            lambda x: x.NotChopp() and x.NotIsotonicWater() and x.HasAmountRemaining()
        )
        
        # Step 3: Mount remount returnable not full
        self.mount_remount_returnable_not_full(snapshot)
        
        # Step 4: Mount isotonic water products
        self.mount_isotonic_water_products(snapshot)
        
        # Step 5: Mount not layer products
        self.mount_not_layer_products(snapshot)
        
        # Count snapshot metrics
        remount_not_splitted_quantity = snapshot.MountedSpaces.IsRemount().NotChopp().count()
        non_palletized_not_splitted_quantity = ItemList(snapshot.GetItems()).NotMarketplace().WithAmountRemaining().count()
        
        # Apply snapshot if it performs better or equal
        if remount_not_splitted_quantity <= remount_quantity and non_palletized_not_splitted_quantity <= not_palletized_quantity:
            self._change_context(context, snapshot)

    def mount_not_layer_products(self, snapshot):
        """C#: MountNotLayerProducts - try to place non-palletized products on layers"""
        # If there are layers and non-palletized items (not marketplace, not chopp)
        if (snapshot.MountedSpaces.IsLayer().any() and 
            ItemList(snapshot.GetItems()).NotMarketplace().NotChopp().WithAmountRemaining().any()):
            
            self.non_layer_on_layer_rule.execute(
                snapshot,
                lambda x: x.NotChopp() and x.HasAmountRemaining(),
                lambda x: x.HasLayer()
            )

    def mount_isotonic_water_products(self, snapshot):
        """C#: MountIsotonicWaterProducts - handle isotonic water allocation with/without min occupation"""
        # First run: with minimum occupation validation
        self.isotonic_water_rule.execute(
            snapshot,
            lambda x: x.NotChopp() and x.IsIsotonicWater() and x.HasAmountRemaining()
        )
        
        # Disable minimum occupation validation
        self.isotonic_water_rule.WithoutMinOccupationValidation()
        
        # Second run: without minimum occupation validation
        self.isotonic_water_rule.execute(
            snapshot,
            lambda x: x.NotChopp() and x.IsIsotonicWater() and x.HasAmountRemaining()
        )
        
        # Third run: conservative attempt if still has items
        if ItemList(snapshot.GetItems()).NotMarketplace().NotChopp().IsIsotonicWater().WithAmountRemaining().any():
            self.isotonic_water_rule.execute(
                snapshot,
                lambda x: x.NotChopp() and x.IsIsotonicWater() and x.HasAmountRemaining()
            )

    def mount_remount_returnable_not_full(self, snapshot):
        """C#: MountRemountReturnableNotFull - create remounts on not-full returnable pallets"""
        # Early exit if no items to process
        if not ItemList(snapshot.GetItems()).NotMarketplace().NotChopp().NotIsotonicWater().WithAmountRemaining().any():
            return
        
        # Execute pallet group/subgroup rule
        self.pallet_group_subgroup_rule.execute(
            snapshot,
            lambda x: x.NotChopp() and x.NotIsotonicWater() and x.HasAmountRemaining()
        )
        
        # Execute returnable/disposable split remount rule
        self.returnable_and_disposable_split_remount_rule.execute(
            snapshot,
            lambda x: x.NotChopp() and x.NotIsotonicWater() and x.HasAmountRemaining()
        )

    def _change_context(self, context, snapshot):
        """Apply snapshot to context (equivalent to C# ChangeContext base method)"""
        # Copy snapshot state to context
        context.Orders = snapshot.Orders
        context.Spaces = snapshot.Spaces
        context.MountedSpaces = snapshot.MountedSpaces

