from .base_rule import BaseRule
from .context import Context    
from typing import Any, List
import logging
from typing import Callable
import json
from pathlib import Path
import pandas as pd 
from ..adapters.logger_instance import logger

class RuleChain:
    """
    Representa uma cadeia de regras que podem ser executadas sequencialmente
    """
    
    def __init__(self, name: str = "DefaultChain"):
        self.name = name
        self.rules: List[BaseRule] = []
        self.logger = logging.getLogger(__name__)
    
    def add_rule(self, rule: BaseRule) -> 'RuleChain':
        """Adiciona uma regra à cadeia"""
        self.rules.append(rule)
        return self

    def there_is_no_method(self, rule: BaseRule) -> bool:
        """Verificar se a regra possui o método should_execute"""
        v = True if getattr(rule, 'should_execute', True) is True else False
        return v

    def run_should_execute(self, rule: BaseRule, context: Context, item_predicate: Callable[[object], bool] = lambda x: True, mounted_space_predicate=None):
        """Verificar se a regra possui o método should_execute e executa-lo.

        Agora aceita os predicados opcionais (compatível com C#).
        """
        function = getattr(rule, 'should_execute', None)
        if callable(function):
            try:
                # return function(context, item_predicate, mounted_space_predicate)
                return function(context)
            except TypeError as e:
                print(str(e))
                # fallback for older rules that only accept (context)
                return function(context)
        return True

    def execute_chain(self, context: Context, item_predicate: Callable[[object], bool] = lambda x: True, mounted_space_predicate=None) -> Context:
        """
        Executa todas as regras da cadeia sequencialmente
        Cada regra pode modificar o contexto antes da próxima execução
        """
        self.logger.info(f"Executando cadeia '{self.name}' com {len(self.rules)} regras")
        
        def _ma_summary(ctx):
            try:
                from ..domain.mounted_space_list import MountedSpaceList
                ms = getattr(ctx, 'mounted_spaces', None) or getattr(ctx, 'MountedSpaces', [])
                driver = sum(x.weight for x in MountedSpaceList(ms).DriverSide())
                helper = sum(x.weight for x in MountedSpaceList(ms).HelperSide())
                total = driver + helper
                pct = driver * 100 / total if total else 0
                return f"M={driver:.2f} ({pct:.2f}%)  A={helper:.2f} ({100-pct:.2f}%)"
            except Exception as e:
                return f"(erro ao calcular M/A: {e})"

        def _bays_summary(ctx):
            try:
                ms = getattr(ctx, 'mounted_spaces', None) or getattr(ctx, 'MountedSpaces', [])
                lines = []
                for space in sorted(ms, key=lambda s: (getattr(s.space, 'number', 0), getattr(s.space, 'side', 0))):
                    sp = space.space
                    side = getattr(getattr(sp, 'sideDesc', None), 'name', None) or getattr(sp, 'side', '?')
                    num = getattr(sp, 'number', '?')
                    w = getattr(space, 'weight', 0)
                    codes = []
                    for c in getattr(space, 'containers', []):
                        for p in getattr(c, 'products', []):
                            codes.append(str(getattr(p, 'Code', getattr(p, 'code', '?'))))
                    lines.append(f"  baia {num}/{side}: w={w:.2f} codes={codes}")
                return "\n".join(lines)
            except Exception as e:
                return f"  (erro bays_summary: {e})"

        for i, rule in enumerate(self.rules):
            rule_name = rule.__class__.__name__
            self.logger.info(f"Executando regra {i+1}/{len(self.rules)}: {rule_name}")

            try:
                # push a node into the hierarchical execution tree
                executed = False
                logger.start_step(1, rule_name, step_type=self.name , registers=None)
                # call should_execute with the optional predicates (backward compatible)
                if self.run_should_execute(rule, context, item_predicate, mounted_space_predicate):
                    try:
                        executed=True
                        _before = _ma_summary(context)

                        try:
                            rule.execute(context)
                            _after = _ma_summary(context)
                            print(f"[MA] {self.name} | {rule_name}: {_before}  →  {_after}")
                            print(f"[BAYS] {rule_name}:\n{_bays_summary(context)}")
                        except Exception as e:
                            import traceback as _tb
                            self.logger.error(f"Erro ao executar regra {rule_name}: {e}")
                            print(f"[ERR] {rule_name}: {e}")
                            _tb.print_exc()
        
                        self.logger.info(f"Regra {rule_name} executada com sucesso")
                        logger.log(f"Regra {rule_name} executada com sucesso")
                        logger.end_step(executed=executed, mounted_spaces=context.MountedSpaces)
                    except Exception as e:
                        try:
                            self.logger.error(f"Erro ao executar regra {rule_name}: {e}")

                        except Exception:
                            pass
                        self.logger.error(f"Erro ao executar regra {rule_name}: {e}")
                        logger.end_step(executed=executed, mounted_spaces=context.MountedSpaces)
                        if self._should_stop_on_error(context):
                            # close node and break
                            try:
                                context.pop_execution_entry('error')
                            except Exception:
                                pass
                            break
                else:
                    self.logger.info(f"Regra {rule_name} não executada! Deve ser ignorada conforme should_execute.")
                    logger.log(f"Regra {rule_name} não executada!")
                    logger.end_step(executed=executed, mounted_spaces=context.MountedSpaces)
                    
                # Verifica se deve parar a execução
                if self._should_stop_chain(context):
                    self.logger.info(f"Parando execução da cadeia após regra {rule_name}")
                    try:
                        context.pop_execution_entry('stopped')
                    except Exception:
                        pass
                    break
            except Exception as e:
                self.logger.error(f"Erro inesperado ao processar regra {rule_name}: {e}")
                pass
        # logger.log(f"Cadeia '{self.name}' executada completamente")
        # logger.end_step(executed=executed, mounted_space=context.MountedSpaces )
        self.logger.info(f"Cadeia '{self.name}' executada completamente")
        return context
    
    def _should_stop_chain(self, context: Context) -> bool:
        """Verifica se a cadeia deve parar baseado no estado do contexto"""
        # Implementar lógica específica de parada
        return False
    
    def _should_stop_on_error(self, context: Context) -> bool:
        """Verifica se deve parar em caso de erro"""
        return False
    
    
    def _get_attr(self, obj: Any, *names, default=None):
        for n in names:
            try:
                val = getattr(obj, n)
                if callable(val):
                    # skip methods
                    continue
                return val
            except Exception:
                pass
        return default

    def mounted_spaces_to_dataframe(self, mounted_spaces: List[Any], export_path: Path = None) -> pd.DataFrame:
        """
        Recebe uma lista de MountedSpace e retorna um pandas.DataFrame com:
        ['mounted_space_id','space_number','space_side','space_side_desc','occupation',
        'product_code','product_name','quantity','packaging','group_code','sub_group_code']
        """
        rows = []
        for ms in mounted_spaces:
            space = self._get_attr(ms, "Space", "space", default=None) or {}
            ms_id = self._get_attr(ms, "Id", "id", default=None)
            space_number = self._get_attr(space, "Number", "number", default=None)
            space_side = self._get_attr(space, "Side", "side", default=None)
            space_size = getattr(space, 'Size', None) or getattr(space, 'size', None)
            space_side_desc = self._get_attr(space, "sideDesc", "sidedesc", "side_desc", default=None)
            try:
                occupation = float(getattr(ms, "Occupation", getattr(ms, "occupation", 0)) or 0.0)
            except Exception:
                occupation = 0.0

            try:
                weight = float(getattr(ms, "Weight", getattr(ms, "_weight", 0)) or 0.0)
            except Exception:
                weight = 0.0

            # determine pallet_code: prefer explicit container code, fallback to composed value
            space_size = str(space_size) if space_size is not None else '0'
            pallet_code = f"P{space_number:02}_{space_side_desc}_{space_number:02d}/{space_size}"

            # use GetProducts() when available, fallback to get_products() or Products
            try:
                products = ms.GetProducts()
            except Exception:
                try:
                    products = ms.get_products()
                except Exception:
                    products = getattr(ms, "Products", getattr(ms, "products", [])) or []

            for mp in products:
                # mp can be a mounted-product wrapper (has Item/Product) or an item
                prod_obj = None
                try:
                    prod_obj = getattr(mp, "Product", None) or getattr(getattr(mp, "Item", None), "Product", None)
                except Exception:
                    prod_obj = None

                # product identifiers
                product_code = self._get_attr(prod_obj, "Code", "code", default=None)
                product_name = self._get_attr(prod_obj, "Name", "name", default=None)
                seqMontagem = self._get_attr(mp, "AssemblySequence", "AssemblySequence", "AssemblySequence", default=0)

                # quantity on mounted product or item
                quantity = self._get_attr(mp, "Amount", "AmountRemaining", "amount", default=None)
                if quantity is None:
                    # try on item inside mp
                    quantity = self._get_attr(getattr(mp, "Item", None), "Amount", "AmountRemaining", "amount", default=None)

                # packaging / group info
                packaging = None
                group_code = None
                sub_group_code = None
                try:
                    packing = getattr(prod_obj, "PackingGroup", None) or getattr(prod_obj, "Packing", None) or getattr(prod_obj, "PalletSetting", None)
                    if packing is not None:
                        packaging = self._get_attr(packing, "Code", "code", default=None)
                        group_code = self._get_attr(packing, "GroupCode", "group_code", default=None)
                        sub_group_code = self._get_attr(packing, "SubGroupCode", "sub_group_code", default=None)
                except Exception:
                    pass

                # product type flags
                is_top = bool(mp.IsTopOfPallet())
                is_returnable = bool(mp.IsReturnable())
                is_isotonic = bool(mp.IsIsotonicWater())
                is_chopp = bool(mp.IsChopp())

                # human-friendly attribute label (match report semantics)
                if is_top:
                    attribute_label = 'TopoPallet'
                elif is_returnable:
                    attribute_label = 'Retornavel'
                elif is_isotonic:
                    attribute_label = 'Isotonico'
                elif is_chopp:
                    attribute_label = 'Chopp'
                else:
                    attribute_label = 'Descartável' if not is_returnable else ''

                rows.append({
                    "pallet_code": pallet_code,
                    "occupation": round(occupation, 2),
                    "weight": round(weight, 2),
                    "product_code": product_code,
                    "product_name": product_name,
                    "quantity": quantity,
                    "packaging": packaging,
                    "group_code": group_code,
                    "sub_group_code": sub_group_code,
                    "is_top_of_pallet": is_top,
                    "is_returnable": is_returnable,
                    "is_isotonic": is_isotonic,
                    "is_chopp": is_chopp,
                    "attribute_label": attribute_label,
                    "seqMontagem":seqMontagem
                })

        df = pd.DataFrame(rows, columns=[
            "pallet_code", "occupation", "weight",
            "product_code","product_name","quantity","packaging","group_code","sub_group_code",
            "is_top_of_pallet","is_returnable","is_isotonic","is_chopp","attribute_label","seqMontagem"
        ])

        if export_path is not None:
            df.sort_values(by=['pallet_code','seqMontagem']).reset_index(drop=True)\
                .to_excel(export_path, index=False)
            
        if export_path is not None:
            # try to write both mounted spaces and not-palletized items into separate sheets
            try:
                np_items = self.context.GetItemsWithAmountRemaining()
                np_rows = []
                for it in np_items:
                    code = it.Code
                    name = it.Product.Name
                    qty = it.AmountRemaining

                    atributo = ''
                    is_top = bool(it.IsTopOfPallet())
                    is_returnable = bool(it.IsReturnable())
                    is_isotonic = bool(it.IsIsotonicWater())
                    is_chopp = bool(it.IsChopp())

                    # human-friendly attribute label (match report semantics)
                    if is_top:
                        atributo = 'TopoPallet'
                    elif is_returnable:
                        atributo = 'Retornavel'
                    elif is_isotonic:
                        atributo = 'Isotonico'
                    elif is_chopp:
                        atributo = 'Chopp'
                    else:
                        atributo = 'Descartável' if not is_returnable else ''
                        
                    np_rows.append({'product_code': str(code), 'product_name': str(name), 'quantity': qty, 'atributo': atributo})

                df_np = pd.DataFrame(np_rows, columns=['product_code', 'product_name', 'quantity', 'atributo'])

                with pd.ExcelWriter(export_path, engine='openpyxl') as writer:
                    df.sort_values(by=['pallet_code', 'seqMontagem']).reset_index(drop=True).to_excel(writer, sheet_name='mounted_spaces', index=False)
                    df_np.to_excel(writer, sheet_name='not_palletized', index=False)
            except Exception:
                # fallback: write mounted spaces only and write not-palletized to a separate file
                df.sort_values(by=['pallet_code','seqMontagem']).reset_index(drop=True).to_excel(export_path, index=False)
                try:
                    csv_np = export_path.with_name(export_path.stem + '_not_palletized.csv')
                    df_np.to_csv(csv_np, index=False)
                except Exception:
                    pass

    
        return df.sort_values(by=['pallet_code','seqMontagem']).reset_index(drop=True)