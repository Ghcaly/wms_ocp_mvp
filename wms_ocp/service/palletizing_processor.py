import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
import logging
from decimal import Context, Decimal
import json
import pandas as pd
from dotenv import load_dotenv

from ..service import apply_boxing 
from ..adapters.database import _log_items_count_by_type, enrich_items, parse_combined_groups 
from ..adapters.palletize_result_mapper import PalletizeResultMapper 
from .calculator_palletizing_service import CalculatorPalletizingService, RuleChain
import requests 
from ..domain.context import (
            Context,
            RouteRuleContext,
            ASRuleContext,
            MixedRuleContext,
            T4RuleContext,
            CrossDockingRuleContext
        )
from .check import run_reports
from .check_xml import run_reports_xml
from .check_txt import run as run_reports_txt
from ..adapters.logger_instance import logger
from .config_generator import ConfigGenerator
from ..adapters.binpack_mapper import apply_binpack_json, BuildActiveBoxesFromBinpack
from ..domain.rule_configuration import build_settings_for_unb_code

# Load environment from .env if present and provide converter host default
load_dotenv()
HOST_CONVERTER = os.getenv('HOST_CONVERTER', 'http://localhost:8081/convert')

class PalletizingProcessor:
    """
    Processador principal de paletização
    Espelha a lógica do CalculatorPalletizingService do C#
    """
    
    def __init__(self, debug_enabled: bool = True):
        self.logger = self._setup_logging(debug_enabled)
        self.palletizing_service = CalculatorPalletizingService()
        self.context: Context = None
        
    def _setup_logging(self, debug_enabled: bool) -> logging.Logger:
        """Configura logging similar ao C#"""
        level = logging.DEBUG if debug_enabled else logging.INFO

        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )

        return logging.getLogger(__name__)

    def type_mapa_input(self, json_path):
        try:
            path = Path(json_path)
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('Type')
        except Exception as e:
            self.logger.error(f"Erro ao determinar tipo do mapa: {e}")
            return None 
    
    def load_configuration_and_data(self, config_file: str, data_file: str) -> Context:
        """
        Carrega configuração e dados - espelha o processo do C#
        
        Args:
            config_file: Arquivo de configuração do mapa (ex: 7fb9588438ea4aa8ac4be1af5aad040b_map_107527.json)
            data_file: Arquivo de dados de entrada (ex: JsonEntradaStackBuilder.json)
        
        Returns:
            Context configurado e carregado
        """
        self.logger.info("=== INICIANDO CARREGAMENTO DE CONFIGURAÇÃO E DADOS ===")
        
        try:
            # Cria contexto com ambos os arquivos
            self.context = self.create_context_for_type(config_file, data_file)
            print(type(self.context))

            print("E Context", type(self.context) == Context) 
            print("E RouteRuleContext", type(self.context) == RouteRuleContext) 
            print("E ASRuleContext", type(self.context) == ASRuleContext) 
            print("E MixedRuleContext", type(self.context) == MixedRuleContext) 
            print("E T4RuleContext", type(self.context) == T4RuleContext) 
            print("E CrossDockingRuleContext", type(self.context) == CrossDockingRuleContext) 

            # Validação básica
            if not self.context.settings:
                raise ValueError("Configurações não carregadas corretamente")
            
            if not self.context.orders:
                raise ValueError("Dados de entrada não carregados corretamente")
            
            self.logger.info(f"✓ Configuração carregada: Mapa {self.context.MapNumber}")
            self.logger.info(f"✓ {len(self.context.settings)} configurações")
            self.logger.info(f"✓ {len(self.context.orders)} orders")
            self.logger.info(f"✓ {len(self.context.not_palletized_items)} itens não paletizados")
            
            return self.context
            
        except Exception as e:
            self.logger.error(f"Erro ao carregar configuração e dados: {e}")
            raise
    
    def create_palletizing_rules_chain(self) -> RuleChain:
        """
        Cria cadeia de regras baseada na configuração - espelha CreateRulesChain do C#
        
        Returns:
            RuleChain configurada dinamicamente
        """
        self.logger.info("=== CRIANDO CADEIA DE REGRAS DE PALETIZAÇÃO ===")
        
        if not self.context:
            raise ValueError("Context não inicializado. Execute load_configuration_and_data primeiro.")
        
        # Cria cadeia baseada nas configurações carregadas
        rules_chain = self.palletizing_service.create_rules_chain_from_context(self.context)
        
        self.logger.info(f"✓ Cadeia criada: '{rules_chain.name}'")
        self.logger.info(f"✓ {len(rules_chain.rules)} regras na cadeia:")
        
        for i, rule in enumerate(rules_chain.rules, 1):
            rule_name = rule.__class__.__name__
            self.logger.info(f"  {i}. {rule_name}")
            
        return rules_chain

    def _extract_debug_node_from_file(self, config_path: Path):
        """Stream-scan config file for a top-level Debug object and return it as a Python object.

        This reads the file in small chunks and balances braces to avoid loading the whole file.
        Returns parsed JSON object or None if not found/parsable.
        """
        try:
            if not config_path.exists():
                return None

            key_names = ['"Debug"', '"debug"']
            chunk_size = 64 * 1024
            with config_path.open('r', encoding='utf-8', errors='ignore') as f:
                buffer = ''
                state = 'search'
                brace_level = 0
                obj_buf = []
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    buffer += chunk
                    pos = 0
                    while pos < len(buffer):
                        if state == 'search':
                            found = -1
                            for key in key_names:
                                idx = buffer.find(key, pos)
                                if idx != -1:
                                    found = idx
                                    break
                            if found == -1:
                                # keep tail
                                buffer = buffer[-50:]
                                break
                            # find opening brace
                            brace_idx = buffer.find('{', found)
                            if brace_idx == -1:
                                buffer = buffer[found:]
                                break
                            state = 'copy'
                            brace_level = 0
                            pos = brace_idx
                        if state == 'copy':
                            ch = buffer[pos]
                            obj_buf.append(ch)
                            if ch == '{':
                                brace_level += 1
                            elif ch == '}':
                                brace_level -= 1
                                if brace_level == 0:
                                    # finished object
                                    raw = ''.join(obj_buf)
                                    try:
                                        return json.loads(raw)
                                    except Exception:
                                        return None
                            pos += 1
                    # continue reading
            return None
        except Exception:
            return None
    
    def execute_palletizing_process(self, rules_chain: RuleChain) -> Context:
        """
        Executa o processo de paletização - espelha ExecuteChain do C#
        
        Args:
            rules_chain: Cadeia de regras a ser executada
            
        Returns:
            Context com resultados da paletização
        """
        self.logger.info(f"=== EXECUTANDO PROCESSO DE PALETIZAÇÃO - Mapa Root {self.context.kind} ===")
        
        # Log estado inicial
        initial_pallets = len(self.context.pallets)
        initial_orders = len(self.context.orders)
        
        self.logger.info(f"Estado inicial:")
        self.logger.info(f"  - Pallets: {initial_pallets}")
        self.logger.info(f"  - Orders: {initial_orders}")
        
        try:
            # Executa a cadeia de regras
            result_context = rules_chain.execute_chain(self.context)
            
            # Log estado final
            final_pallets = len(result_context.pallets)
            final_orders = len(result_context.orders)
            
            self.logger.info(f"Estado final:")
            self.logger.info(f"  - Pallets: {final_pallets} (Δ +{final_pallets - initial_pallets})")
            self.logger.info(f"  - Orders: {final_orders}")
            
            # Log detalhado dos mounted spaces criados (pallets no contexto do negócio)
            if result_context.MountedSpaces:
                self.logger.info("✓ Mounted Spaces criados (Pallets):")
                for i, mounted_space in enumerate(result_context.MountedSpaces):
                    try:
                        # Acessa informações do Space (baia/lado)
                        space = mounted_space.Space
                        lado = getattr(space, 'Side', getattr(space, 'side', 'N/A'))
                        baia = getattr(space, 'Number', getattr(space, 'number', 'N/A'))
                        
                        # Conta produtos em todos os containers deste mounted space
                        total_products = 0
                        for container in mounted_space.Containers:
                            total_products += len(container.Products)
                        
                        occupation = getattr(mounted_space, 'Occupation', getattr(mounted_space, 'occupation', 0))
                        
                        self.logger.info(
                            f"  MountedSpace {i+1}: "
                            f"Lado={lado}, Baia={baia}, "
                            f"Occupation={occupation:.2f}, "
                            f"Products={total_products}"
                        )
                    except Exception as e:
                        self.logger.warning(f"  MountedSpace {i+1}: Erro ao exibir detalhes - {e}")
            
            return result_context
            
        except Exception as e:
            self.logger.error(f"Erro durante execução da paletização: {e}")
            raise
    
    def generate_output_reports(self, context: Context, output_dir: str = None) -> Dict[str, str]:
        """
        Gera relatórios de saída - espelha geração de outputs do C#
        
        Args:
            context: Contexto com resultados
            output_dir: Diretório de saída (opcional)
            
        Returns:
            Dict com caminhos dos arquivos gerados
        """
        self.logger.info("=== GERANDO RELATÓRIOS DE SAÍDA ===")
        
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / 'data'
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(exist_ok=True)
        
        outputs = {}
        
        try:
            # 1. Relatório Excel/CSV
            excel_file = output_dir / f'palletizing_result_map_{context.MapNumber}.xlsx'
            excel_result = context.to_xlsx(excel_file)
            outputs['excel'] = str(excel_file)
            self.logger.info(f"✓ {excel_result}")
            
            # 2. Relatório JSON
            json_file = output_dir / f'palletizing_result_map_{context.MapNumber}.json'
            json_content = context.to_json(indent=2)
            with open(json_file, 'w', encoding='utf-8') as f:
                f.write(json_content)
            outputs['json'] = str(json_file)
            self.logger.info(f"✓ JSON salvo: {json_file}")
            
            # 3. Relatório XML
            xml_file = output_dir / f'palletizing_result_map_{context.MapNumber}.xml'
            xml_content = context.to_xml(pretty=True)
            with open(xml_file, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            outputs['xml'] = str(xml_file)
            self.logger.info(f"✓ XML salvo: {xml_file}")
            
            # 4. Relatório de Summary
            summary_file = output_dir / f'palletizing_summary_map_{context.MapNumber}.txt'
            summary_content = self._generate_summary_report(context)
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(summary_content)
            outputs['summary'] = str(summary_file)
            self.logger.info(f"✓ Summary salvo: {summary_file}")
            
            return outputs
            
        except Exception as e:
            self.logger.error(f"Erro ao gerar relatórios: {e}")
            raise
    
    def _generate_summary_report(self, context: Context) -> str:
        """Gera relatório resumo textual"""
        lines = []
        lines.append("=== RELATÓRIO DE PALETIZAÇÃO ===")
        lines.append(f"Mapa: {context.MapNumber}")
        lines.append(f"Empresa: {context.empresa}")
        lines.append(f"Filial: {context.filial}")
        lines.append("")
        
        lines.append("=== CONFIGURAÇÕES PRINCIPAIS ===")
        important_settings = [
            'EnableSafeSideRule', 'SideBalanceRule', 'GroupComplexLoads',
            'PalletEqualizationRule', 'MinimumVolumeInComplexLoads'
        ]
        for setting in important_settings:
            value = context.get_setting(setting, 'N/A')
            lines.append(f"{setting}: {value}")
        lines.append("")
        
        lines.append("=== RESULTADOS ===")
        lines.append(f"Total de Orders processadas: {len(context.orders)}")
        lines.append(f"Total de Pallets criados: {len(context.pallets)}")
        lines.append("")
        
        if context.pallets:
            lines.append("=== DETALHES DOS PALLETS ===")
            for i, pallet in enumerate(context.pallets):
                lines.append(f"Pallet {i+1}:")
                lines.append(f"  - Lado: {pallet.cdLado}")
                lines.append(f"  - Baia/Gaveta: {pallet.nrBaiaGaveta}")
                lines.append(f"  - Itens: {len(pallet.Products)}")
                
                for j, item in enumerate(pallet.Products):
                    lines.append(f"    Item {j+1}: SKU={item.cdItem}, Qty={item.qtUnVenda}")
                lines.append("")
        
        return '\n'.join(lines)

    def _generate_detailed_text_report(self, context: Context, output_dir: str = None) -> str:
        """Generate a more detailed textual pallet report similar to the C# output.

        This is a best-effort formatter that iterates `context.pallets` and
        writes a human-readable text file with pallet headers and item lines.
        The goal is to produce a file comparable to the project's example like
        `107527-ocp-AS.txt`.
        """
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / 'data' / (context.context_kind.lower() if getattr(context, 'context_kind', None) else '')
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # choose filename similar to example: {mapNumber}-ocp-{ContextKind}.txt
        kind = getattr(context, 'context_kind', 'map') or 'map'
        file_name = f"{context.MapNumber}-ocp-{kind}.txt"
        out_path = output_dir / file_name

        lines = []
        lines.append(f"Mapa: {context.MapNumber} Veículo: {getattr(context, 'vehicle', '')}")
        # basic totals if available
        try:
            total_products = sum(len(ms.get_products()) for ms in getattr(context, 'mounted_spaces', []) or [])
        except Exception:
            total_products = 0
        lines.append(f"Produtos: {total_products}")
        lines.append("")
        lines.append("DETALHAMENTO DE PALETAS")
        lines.append("")

        # Sort mounted spaces by bay number then side for stable output
        mspaces = list(getattr(context, 'mounted_spaces', []) or [])
        try:
            mspaces = sorted(mspaces, key=lambda m: (getattr(getattr(m, 'space', None), 'number', 0) or 0, str(getattr(getattr(m, 'space', None), 'side', ''))))
        except Exception:
            pass

        for ms in mspaces:
            sp = getattr(ms, 'space', None)
            nr = getattr(sp, 'number', '')
            lado = getattr(sp, 'side', '')
            occ = getattr(ms, 'occupation', getattr(ms, 'Ocupacao', 0))

            # compute total weight and total qty for this mounted space
            total_weight = 0.0
            total_qty = 0
            # aggregate products by SKU/code so each SKU appears once per pallet (like C# output)
            agg = {}

            products = []
            try:
                products = ms.get_products() if hasattr(ms, 'get_products') else getattr(ms, 'products', []) or []
            except Exception:
                products = getattr(ms, 'products', []) or []

            for p in products:
                # p could be an Item or a wrapper; try to normalize
                item = p
                prod = getattr(p, 'product', None) or getattr(p, 'prod', None) or None
                if prod is None and hasattr(p, 'code') and hasattr(p, 'amount'):
                    prod = getattr(p, 'product', None)

                # extract fields with best-effort fallbacks
                code = getattr(prod, 'code', None) or getattr(item, 'code', None) or getattr(item, 'cdItem', None) or ''
                name = getattr(prod, 'name', None) or (getattr(item, 'raw', {}) or {}).get('dsItem') if getattr(item, 'raw', None) else None
                if not name:
                    name = getattr(prod, 'name', None) or getattr(item, 'name', None) or ''

                qty = getattr(item, 'amount', None) or getattr(item, 'qtUnVenda', None) or getattr(item, 'qt_un_venda', None) or getattr(prod, 'quantity', 1) or 1
                try:
                    qty = int(qty)
                except Exception:
                    try:
                        qty = int(float(qty))
                    except Exception:
                        qty = 0

                # embalagem / packing info
                embalagem = ''
                try:
                    ps = getattr(prod, 'pallet_setting', None) or (getattr(item, 'raw', {}) or {}).get('PalletSetting') if getattr(item, 'raw', None) else None
                    if isinstance(ps, dict):
                        embalagem = ps.get('PalletQuantity') or ps.get('palletQuantity') or ps.get('PalletQuantityDozen') or ''
                    else:
                        embalagem = getattr(prod, 'pallet_quantity', '')
                except Exception:
                    embalagem = ''

                # group/sub info
                grp_sub = ''
                try:
                    g = getattr(prod, 'packing_group_id', None) or getattr(prod, 'packing_group_description', None)
                    if g:
                        grp_sub = str(g)
                except Exception:
                    grp_sub = ''

                # unit weight
                unit_weight = None
                try:
                    w_unit = getattr(prod, 'weight', None) or getattr(prod, 'gross_weight', None) or None
                    if w_unit is not None:
                        unit_weight = float(w_unit)
                except Exception:
                    unit_weight = None

                # attribute (Retornavel / Descartavel / TopoPallet / etc)
                atributo = ''
                try:
                    if getattr(prod, 'is_returnable', False) or getattr(prod, 'is_returnable', None) is True:
                        atributo = 'Retornavel'
                    elif getattr(prod, 'is_disposable', False) or getattr(prod, 'is_disposable', None) is True or getattr(prod, 'is_disposable', None):
                        atributo = 'Descartável'
                    elif getattr(prod, 'pallet_top', False) or getattr(prod, 'pallet_top', None):
                        atributo = 'TopoPallet'
                    elif getattr(prod, 'is_chopp', False) or getattr(prod, 'is_chopp', None):
                        atributo = 'Chopp'
                except Exception:
                    atributo = ''

                # ocupacao per unit (best effort)
                occ_unit = getattr(p, 'occupation', None) or getattr(p, 'ocupacao', None) or getattr(prod, 'total_area_occupied_by_unit', None)
                try:
                    occ_unit = float(occ_unit) if occ_unit is not None else None
                except Exception:
                    occ_unit = None

                key = code or f"__unknown__:{name}"
                if key not in agg:
                    agg[key] = {
                        'code': code,
                        'name': name or '',
                        'qty': int(qty),
                        'embalagem': embalagem or '',
                        'grp_sub': grp_sub or '',
                        'total_weight': (unit_weight * qty) if unit_weight is not None else None,
                        'unit_weight': unit_weight,
                        'atributo': atributo,
                        'total_occupacao': (occ_unit * qty) if occ_unit is not None else None,
                        'unit_occupacao': occ_unit,
                    }
                else:
                    agg[key]['qty'] += int(qty)
                    if unit_weight is not None:
                        if agg[key]['total_weight'] is None:
                            agg[key]['total_weight'] = unit_weight * qty
                        else:
                            agg[key]['total_weight'] += unit_weight * qty
                    if occ_unit is not None:
                        if agg[key]['total_occupacao'] is None:
                            agg[key]['total_occupacao'] = occ_unit * qty
                        else:
                            agg[key]['total_occupacao'] += occ_unit * qty

                # accumulate totals
                if unit_weight is not None:
                    total_weight += (unit_weight * qty)
                total_qty += int(qty)

            # build prod_lines from aggregated values preserving order by total qty desc
            prod_lines = []
            for v in sorted(agg.values(), key=lambda x: -x['qty']):
                prod_lines.append({
                    'code': v['code'],
                    'name': v['name'],
                    'qty': v['qty'],
                    'embalagem': v['embalagem'],
                    'grp_sub': v['grp_sub'],
                    'weight': v['total_weight'],
                    'atributo': v['atributo'],
                    'ocupacao': v['total_occupacao'],
                })

            # header line: try to mimic sample structure when possible
            header = f"P_{('A' if str(lado).upper().startswith('L') else 'M')}_{str(nr).zfill(2)}_1/{getattr(sp, 'size', '')} - {float(occ):.2f} - {total_qty}  Peso: {total_weight:.2f}"
            lines.append(header)
            lines.append("            |============================ Produtos da área de separação: Geral ===================================================================|")

            # product table header (columns)
            # format: index(=0) code name qty embalagem grp/sub peso atributo ocupacao
            for pl in prod_lines:
                code = str(pl['code']) if pl['code'] is not None else ''
                name = pl['name'][:42].ljust(42)
                qty = str(pl['qty']).rjust(8)
                emb = str(pl['embalagem']).ljust(9)
                grp = str(pl['grp_sub']).ljust(7)
                peso = f"{(pl['weight'] or 0):.2f}".rjust(10) if pl['weight'] is not None else ''.rjust(10)
                atr = pl['atributo'].ljust(13)
                ocu = f"{(pl['ocupacao'] or '')}".rjust(11)
                lines.append(f"            | 0       {code:13} {name} {qty} {emb} {grp} {peso} {atr} {ocu} | ")

            lines.append("            |                                                                                                                                     |")
            lines.append("            |=====================================================================================================================================|")
            lines.append("")

        # Append not-palletized items section
        if getattr(context, 'not_palletized_items', None):
            lines.append("ITENS NÃO PALETIZADOS:")
            for np in context.not_palletized_items:
                code = np.get('cdItem') or np.get('Code') or np.get('cd_item') or ''
                qty = np.get('qtUnVenda') or np.get('Quantity') or np.get('qt_un_venda') or 0
                lines.append(f"{code:20}  Qty: {qty}")

        with out_path.open('w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        return str(out_path)
    
    def create_context_for_type(self, config_file: str, data_file: str):
        
        def type_map(num: int) -> str:
            tipo_map = {1: "Rota", 2: "AS", 3: "CrossDocking", 4: "Mixed", 5: "T4"}
            return tipo_map.get(num, "Desconhecido")

        kind = type_map(self.type_mapa_input(data_file))

        cls_map = {
            "Rota": RouteRuleContext,
            "AS": ASRuleContext,
            "CrossDocking": RouteRuleContext,
            "Mixed": MixedRuleContext,
            "T4": T4RuleContext,
            "CrossDocking": CrossDockingRuleContext
        }

        ctx_cls = cls_map.get(kind, Context)
        return  ctx_cls(
                    config_path=config_file,
                    json_path=data_file,
                )

    def gerar_arquivos_jsons(self, saved_path: str, input_file: str, config_file: str):
        """Prepara arquivos necessários - FLUXO COMPLETO"""
        print("=" * 80)
        print(f"🐛 Preparando arquivos de entrada jsons")
        print("=" * 80)
        print("")

        try:
            with open(saved_path, 'rb') as f:
                response = requests.post(
                    HOST_CONVERTER,
                    files={'file': (Path(saved_path).name, f, 'application/xml')},
                    timeout=30
                )
            
            if response.status_code == 200:
                with open(input_file, 'w', encoding='utf-8') as f:
                    json.dump(response.json(), f, indent=2, ensure_ascii=False)
                print(f"  ✓ JSON salvo: {input_file}")
            else:
                raise Exception(f"Converter retornou erro: {response.status_code}")
        
        except requests.exceptions.ConnectionError:
            print("  ❌ Converter não está rodando!")
            print("  Inicie com: cd wms_converter && python api.py")
            raise
    

        print("⚙️  PASSO 3: Gerando configuração") 
        
        try:  
            path = Path(__file__).parent.parent
            generator = ConfigGenerator(database_path=path / "database")
            generator.generate_config_file(
                input_file=input_file,
                output_file=config_file,
                overwrite=True
            )
            # csv_path = Path(__file__).parent.parent / 'database' / 'ruleconfiguration_12012026.csv'
            # settings = build_settings_for_unb_code(csv_path, "970")
            # print(json.dumps(settings, indent=2, ensure_ascii=False))
            # settings = build_settings_for_unb_code(csv_path, "401")
            # print(json.dumps(settings, indent=2, ensure_ascii=False))
            # settings = build_settings_for_unb_code(csv_path, "916")
            # print(json.dumps(settings, indent=2, ensure_ascii=False))
        except Exception as e: 
            print(f"  ❌ Erro ao gerar config: {e}")
            raise


    def run_complete_palletizing_process(self, config_file: str, data_file: str, output_dir: str = None, validation_file: str = None) -> Dict[str, Any]:
        """
        Executa o processo completo de paletização - método principal espelhado no C#
        
        Args:
            config_file: Arquivo de configuração
            data_file: Arquivo de dados
            output_dir: Diretório de saída
            
        Returns:
            Dict com resultados e caminhos dos arquivos gerados
        """
        self.logger.info("🚀 INICIANDO PROCESSO COMPLETO DE PALETIZAÇÃO")
        
        try:

            # 1. Carrega configuração e dados
            self.load_configuration_and_data(config_file, data_file)
            
            # 2. Consultar banco de dados
            # database.
            # file = r"C:\Users\BRKEY864393\Downloads\csv-itens (1).csv"
            base_dir = Path(__file__).parent.parent / 'database'
            file = base_dir / "csv-itens-19012026.csv"
            df = pd.read_csv(file, sep=';')
            df = df.where(pd.notnull(df), None).astype(object)
            df['Código'] = df['Código'].astype(str)
            df['Código Unb'] = df['Código Unb'].astype(str)
            
            all_items = []
            i=0
            for order in self.context.orders:
                print(f"Enriquecendo items da order {i+1}/{len(self.context.orders)}")
                order.Items = enrich_items(order.Items, parse_combined_groups(self.context.get_setting('CombinedGroups', [])), order.SupportPoint, df[df['Id Catálogo']==2].set_index("Código"))
                # apply_combined_groups_to_product(order.Items, self.context.get_setting('CombinedGroups', []))
                all_items.extend(order.Items)
                i=i+1
            _log_items_count_by_type(all_items)

            if self.context.kind != "Route":
                print(f"Esse mapa nao eh de Rota. Tipo : {self.context.kind}")
                return 
            
            # 3. Cria cadeia de regras
            match self.context.kind:
                case "Route":
                    self.context.merge_orders_in_place()
                    result_context = self.execute_palletizing_process(self.palletizing_service.principal_route_chain)
                case "AS":
                    result_context = self.execute_palletizing_process(self.palletizing_service.as_chain)
                case "Mixed":
                    result_context = self.execute_palletizing_process(self.palletizing_service.mixed_chain)
                case "CrossDocking":
                    result_context = self.execute_palletizing_process(self.palletizing_service.crossdocking_chain)
                case "T4":
                    result_context = self.execute_palletizing_process(self.palletizing_service.t4_chain)
            
            # salvar results antes das regras de common
            # df =  self.mounted_spaces_to_dataframe(self.context.MountedSpaces, Path(f"./antes_do_common.xlsx"))

            result_context = self.execute_palletizing_process(self.palletizing_service.common_chain)

            out_path = str(Path(output_dir) / f'palletize_result_map_{result_context.palletize_dto.document_number }.json')

            try:
                #temporario, reverter o merge da order
                self.context.reattach_original_orders_to_mounted_products()
            except Exception as e:
                self.logger.error(f"Erro ao reverter merge das orders: {e}")

            # Use the PalletizeResultMapper to build and save the canonical output.json
            try:
                PalletizeResultMapper.save(self.context, out_path)
                self.logger.info(f"✓ PalletizeResult saved: {out_path}")
            except Exception as e:
                self.logger.error(f"Erro ao gerar PalletizeResultEvent via PalletizeResultMapper: {e}")
                raise

            # Gerar resumo de paletes (.txt) a partir do JSON salvo
            try:
                from ..adapters.generate_pallet_summary import load_json, write_full_report
                json_path = Path(out_path)
                data = load_json(json_path)
                txt_path = json_path.with_suffix('.txt')
                write_full_report(data, txt_path)
                self.logger.info(f"✓ Pallet summary saved: {txt_path}")
            except Exception as e:
                self.logger.error(f"Erro ao gerar resumo de paletes: {e}")

            # try:
            #     df =  self.mounted_spaces_to_dataframe(self.context.MountedSpaces, Path(f"./final.xlsx"))
            # except Exception as e:
            #     self.logger.error(f"Erro ao executar exportação para Excel: {e}")


            # additionally generate the detailed text report (secondary output)
            # try:
            #     detailed_path = PalletizeTextReport.save_text(self.context, Path(output_dir))
            #     self.logger.info(f"✓ Detailed text report saved: {detailed_path}")
            # except Exception as e:
            #     self.logger.error(f"Erro ao gerar relatório textual detalhado: {e}")

            # Prefer JSON validation when provided; if missing, try XML variant and use CheckXML
            try:
                validation_path = Path(validation_file) if validation_file else None
                if validation_path and validation_path.exists():
                    run_reports(map_json=out_path, output_json=validation_file, input_json=data_file)
                else:
                    # derive xml path by replacing .json with .xml (or use out_path with .xml)
                    if validation_file:
                        txt_path = Path(validation_file).with_suffix('.txt')
                    else:
                        txt_path = Path(out_path).with_suffix('.txt')

                    try:
                        rc = run_reports_txt(txt_path=str(txt_path), map_json_path=out_path, input_path=data_file)
                        if rc == 0:
                            self.logger.info(f"✓ XML validation OK: {txt_path}")
                        else:
                            self.logger.warning(f"XML validation returned code {rc}: {txt_path}")
                    except Exception as e:
                        self.logger.error(f"Erro ao validar via XML com CheckXML: {e}")
            except Exception as e:
                self.logger.error(f"Erro ao executar validação de saída: {e}")
            
            # map = convert_context(result_context)

            # result_context.pallets = map.get("pallets", [])
            # # 4. Gera relatórios
            # output_files = self.generate_output_reports(result_context, output_dir)
            # # 4b. Gera relatório textual detalhado (formato similar ao arquivo de saída esperado)
            # try:
            #     detailed_path = self._generate_detailed_text_report(result_context, output_dir)
            #     if detailed_path:
            #         output_files['detailed_txt'] = detailed_path
            #         self.logger.info(f"✓ Detailed TXT salvo: {detailed_path}")
            # except Exception:
            #     # non-fatal: continue
            #     pass
            
            # 5. Resultado final
            result = {
                'success': True,
                'context': result_context,
                'statistics': {
                    'orders_processed': len(result_context.orders),
                    'pallets_created': len(result_context.pallets),
                    'total_items': sum(len(p.Products) for p in result_context.pallets),
                    'map_number': result_context.MapNumber
                },
                # 'output_files': output_files
            }
            
            # `context` is your runtime Context instance (the object you use while running rules)
            # event = build_palletize_result_event(result_context, palletize_dto=None, request=None, success=True, message=None)

            # Quick in-memory JSON
            # json_text = to_json(event, indent=2)
            # print(json_text[:200])  # preview

            # out_path = save_palletize_report_on_storage(event, path="data/palletize_result_preview.json")
            # print("Saved JSON to:", out_path)

            self.logger.info("✅ PROCESSO DE PALETIZAÇÃO CONCLUÍDO COM SUCESSO")
            self.logger.info(f"📊 Estatísticas: {result['statistics']}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ ERRO NO PROCESSO DE PALETIZAÇÃO: {e}")
            return {
                'success': False,
                'error': str(e),
                'context': self.context,
                'statistics': {},
                'output_files': {}
            }

    def run(self):
        """
        Função principal - espelha a execução do C#
        """
        print("=" * 80)
        print("🏭 SISTEMA DE PALETIZAÇÃO - VERSÃO PYTHON")
        print("Baseado no sistema C# original")
        print("=" * 80)
        
        # Caminhos dos arquivos
        completo = True

        # MODIFICADO: Aceitar MAPA_NUM via variável de ambiente
        import os
        mapa_env = os.getenv('MAPA_NUM')
        
        if mapa_env:
            # Usar mapa da variável de ambiente
            base_dir = Path(__file__).parent.parent / f'data/route/{mapa_env}'
            print(f"📍 Processando mapa via MAPA_NUM: {mapa_env}")
        else:
            # Fallback para valor hardcoded original
            base_dir = Path(__file__).parent.parent / 'data/crossDocking'
            base_dir = Path(__file__).parent.parent / 'data/as'
            # base_dir = Path(__file__).parent.parent / 'data/route/612481' ## 85# lembrar de alterar as informacoes de camada para zero
            # # base_dir = Path(__file__).parent.parent / 'data/route/612479' 
            # base_dir = Path(__file__).parent.parent / 'data/route/620768' ## 19%
            # # base_dir = Path(__file__).parent.parent / 'data/route/620821'
            base_dir = Path(__file__).parent.parent / 'data/route/620807'
            # base_dir = Path(__file__).parent.parent / 'data/route/621387'
            # base_dir = Path(__file__).parent.parent / 'data/route/621425'#choop

            # base_dir = Path(__file__).parent.parent / 'data/route/621337'#estava 0%, ok agr
            # base_dir = Path(__file__).parent.parent / 'data/route/621345'#complexgroup
            # base_dir = Path(__file__).parent.parent / 'data/route/621334'#apenas ordenacao no palletgroup, ok agr
            # base_dir = Path(__file__).parent.parent / 'data/route/621191'#palletgroup, separando 1 item apenas
            # base_dir = Path(__file__).parent.parent / 'data/route/621287'#ok
            # base_dir = Path(__file__).parent.parent / 'data/route/621341'# estava dividindo, 
            # base_dir = Path(__file__).parent.parent / 'data/route/621195'
            # base_dir = Path(__file__).parent.parent / 'data/route/620768' ## 19%
            # base_dir = Path(__file__).parent.parent / 'data/route/621425'
            # base_dir = Path(__file__).parent.parent / 'data/route/621622'
            # base_dir = Path(__file__).parent.parent / 'data/route/621588'
            # base_dir = Path(__file__).parent.parent / 'data/route/620807'#85.4%
            base_dir = Path(__file__).parent.parent / 'data/route/620768'
            # base_dir = Path(__file__).parent.parent / 'data/route/621563'
            # base_dir = Path(__file__).parent.parent / 'data/route/621425'
            # base_dir = Path(__file__).parent.parent / 'data/route/622517'
        
        

        config_file = base_dir / 'config_completo.json'
        data_file = base_dir / 'input.json'
        validacao_file = base_dir / 'output.json'
        output_dir = base_dir / 'output'
        
        if completo:
            # config_file = base_dir / 'config_completo.json'
            # data_file = base_dir / 'inputcompleto.json'
            config_file = base_dir / 'config.json'
            data_file = base_dir / 'input.json'

        # Verifica se arquivos existem
        if not config_file.exists():
            print(f"❌ Arquivo de configuração não encontrado: {config_file}")
            return 1
        
        if not data_file.exists():
            print(f"❌ Arquivo de dados não encontrado: {data_file}")
            return 1
        
        # Executa processo completo na própria instância (não criar nova instância)
        # logger.save()
        result = self.run_complete_palletizing_process(
            config_file=str(config_file),
            data_file=str(data_file),
            output_dir=str(output_dir),
            validation_file=str(validacao_file)
        )
        
        # save logger file into the same output directory used for palletization
        try:
            map_number = None
            try:
                ctx = result.get('context')
                map_number = getattr(ctx, 'MapNumber', None)
            except Exception:
                map_number = None

            if map_number:
                dest = Path(output_dir) / f'process_log_map_{map_number}.json'
                resultado = logger.save(str(dest))
            else:
                resultado = logger.save(output_dir)
        except Exception:
            resultado = logger.save()
        
        # print("Arquivo gerado:", resultado)

        # Resultado final
        if result['success']:
            print("\n" + "=" * 80)
            print("✅ PALETIZAÇÃO CONCLUÍDA COM SUCESSO!")
            print("=" * 80)
            
            stats = result['statistics']
            print(f"📈 Orders processadas: {stats['orders_processed']}")
            print(f"📦 Pallets criados: {stats['pallets_created']}")
            print(f"📋 Total de itens: {stats['total_items']}")
            print(f"🗺️ Mapa número: {stats['map_number']}")
            
            print("\n📁 Arquivos gerados:")
            # for file_type, file_path in result['output_files'].items():
            #     print(f"  - {file_type.upper()}: {file_path}")
            
            return self.context
        else:
            print("\n" + "=" * 80)
            print("❌ ERRO NA PALETIZAÇÃO!")
            print("=" * 80)
            print(f"Erro: {result['error']}")
            return 1


    
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
                quantity = mp.Amount
                if quantity is None:
                    # try on item inside mp
                    quantity = getattr(getattr(mp, "Item", None), "Amount", None)

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
    
    def save_xml_input(self, xml_content: Union[bytes, str], filename: Optional[str] = None) -> Path:
        """Save incoming XML into data/xml_in and return saved Path."""
        base_dir = Path(__file__).parent.parent / 'data' / 'xml_in'
        base_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            ts = int(time.time() * 1000)
            filename = f"input_{ts}.xml"

        dest = base_dir / filename
        try:
            if isinstance(xml_content, (bytes, bytearray)):
                dest.write_bytes(xml_content)
            else:
                dest.write_text(str(xml_content), encoding='utf-8')
            self.logger.info(f"✓ XML salvo em: {dest}")
            return dest
        except Exception as e:
            self.logger.error(f"Erro ao salvar XML na pasta xml_in: {e}")
            raise

    def execute_palletization(self, config_file: str, data_file: str, output_dir: Optional[str] = None, validation_file: Optional[str] = None) -> Dict[str, Any]:
        """Wrapper to call the main palletization pipeline from external callers/endpoints."""
        # return self.run_complete_palletizing_process(config_file=config_file, data_file=data_file, output_dir=output_dir, validation_file=validation_file)
        """
        Executa o processo completo de paletização - método principal espelhado no C#
        
        Args:
            config_file: Arquivo de configuração
            data_file: Arquivo de dados
            output_dir: Diretório de saída
            
        Returns:
            Dict com resultados e caminhos dos arquivos gerados
        """
        self.logger.info("🚀 INICIANDO PROCESSO COMPLETO DE PALETIZAÇÃO")
        
        try:
            # 1. Carrega configuração e dados
            self.load_configuration_and_data(config_file, data_file)
            
            base_dir = Path(__file__).parent.parent / 'database'
            file = base_dir / "csv-itens-19012026.csv"
            df = pd.read_csv(file, sep=';')
            df = df.where(pd.notnull(df), None).astype(object)
            df['Código'] = df['Código'].astype(str)
            df['Código Unb'] = df['Código Unb'].astype(str)
            
            all_items = []
            i=0
            for order in self.context.orders:
                print(f"Enriquecendo items da order {i+1}/{len(self.context.orders)}")
                order.Items = enrich_items(order.Items, parse_combined_groups(self.context.get_setting('CombinedGroups', [])), order.SupportPoint, df[df['Id Catálogo']==2].set_index("Código"))
                # apply_combined_groups_to_product(order.Items, self.context.get_setting('CombinedGroups', []))
                all_items.extend(order.Items)
                i=i+1
            _log_items_count_by_type(all_items)

            if self.context.kind != "Route":
                print(f"Esse mapa nao eh de Rota. Tipo : {self.context.kind}")
                return 
            
            self.logger.info("=== APLICANDO BOXING VIA API ===")
            result = apply_boxing.apply_boxing_2(self.context.orders, df[df['Id Catálogo']==2].set_index("Código"))

            # 3. Aplicar resultado do Binpack no Context (100% fiel ao C#)
            self.logger.info("=== PROCESSANDO RESULTADO DO BINPACK ===")
            created_items, marketplace_codes = [], []
            if result!=1:  
                # Preparar parâmetros
                items_request = []  # Lista de Item com metadados (equivalente ao ItemDto[] do C#)
                for order in self.context.orders:
                    items_request.extend(order.Items)

                groups = parse_combined_groups(self.context.get_setting('CombinedGroups', []))  # GroupCombinationDto[]
                active_boxes = BuildActiveBoxesFromBinpack(result, groups)

                # Aplicar binpack JSON no context (equivalente ao ToEnumerableOfIOrder do C#)
                created_items, marketplace_codes = apply_binpack_json(
                    binpack_json=result,  # Resultado da API de binpack
                    context=self.context,  # Context com orders
                    items_request=items_request,  # Metadados dos items
                    groups=groups,  # Grupos combinados
                    active_boxes=active_boxes  # Boxes ativas
                )

                self.logger.info(f"✓ Binpack processado:")
                self.logger.info(f"  - {len(created_items)} novos items criados (Package/BoxTemplate)")
                self.logger.info(f"  - {len(marketplace_codes)} códigos marketplace")
                self.logger.info(f"  - Items originais filtrados automaticamente")

                # Log tipos de items após binpack
                print(len(self.context.get_all_items()))
                _log_items_count_by_type(self.context.get_all_items())

            
            # 3. Cria cadeia de regras
            match self.context.kind:
                case "Route":
                    self.context.merge_orders_in_place(created_items, marketplace_codes)
                    result_context = self.execute_palletizing_process(self.palletizing_service.principal_route_chain)
                case "AS":
                    result_context = self.execute_palletizing_process(self.palletizing_service.as_chain)
                case "Mixed":
                    result_context = self.execute_palletizing_process(self.palletizing_service.mixed_chain)
                case "CrossDocking":
                    result_context = self.execute_palletizing_process(self.palletizing_service.crossdocking_chain)
                case "T4":
                    result_context = self.execute_palletizing_process(self.palletizing_service.t4_chain)
            
            result_context = self.execute_palletizing_process(self.palletizing_service.common_chain)

            out_path = str(Path(output_dir) / f'palletize_result_map_{result_context.palletize_dto.document_number }.json')

            try:
                self.context.reattach_original_orders_to_mounted_products()
            except Exception as e:
                self.logger.error(f"Erro ao reverter merge das orders: {e}")

            try:
                PalletizeResultMapper.save(self.context, out_path)
                self.logger.info(f"✓ PalletizeResult saved: {out_path}")
            except Exception as e:
                self.logger.error(f"Erro ao gerar PalletizeResultEvent via PalletizeResultMapper: {e}")
                raise

            # Gerar resumo de paletes (.txt) a partir do JSON salvo
            try:
                from ..adapters.generate_pallet_summary import load_json, write_full_report
                json_path = Path(out_path)
                data = load_json(json_path)
                txt_path = json_path.with_suffix('.txt')
                write_full_report(data, txt_path)
                self.logger.info(f"✓ Pallet summary saved: {txt_path}")
            except Exception as e:
                self.logger.error(f"Erro ao gerar resumo de paletes: {e}")

            # Prefer JSON validation when provided; if missing, try XML variant and use CheckXML
            try:
                validation_path = Path(validation_file) if validation_file else None
                if validation_path and validation_path.exists():
                    run_reports(map_json=out_path, output_json=validation_file, input_json=data_file)
                else:
                    # derive xml path by replacing .json with .xml (or use out_path with .xml)
                    if validation_file:
                        txt_path = Path(validation_file).with_suffix('.txt')
                    else:
                        txt_path = Path(out_path).with_suffix('.txt')

                    try:
                        rc = run_reports_txt(txt_path=str(txt_path), map_json_path=out_path, input_path=data_file)
                        if rc == 0:
                            self.logger.info(f"✓ XML validation OK: {txt_path}")
                        else:
                            self.logger.warning(f"XML validation returned code {rc}: {txt_path}")
                    except Exception as e:
                        self.logger.error(f"Erro ao validar via XML com CheckXML: {e}")
            except Exception as e:
                self.logger.error(f"Erro ao executar validação de saída: {e}")
            
            # 5. Resultado final
            result = {
                'success': True,
                'context': result_context,
                'statistics': {
                    'orders_processed': len(result_context.orders),
                    'pallets_created': len(result_context.pallets),
                    'total_items': sum(len(p.Products) for p in result_context.pallets),
                    'map_number': result_context.MapNumber
                },
            }

            self.logger.info("✅ PROCESSO DE PALETIZAÇÃO CONCLUÍDO COM SUCESSO")
            self.logger.info(f"📊 Estatísticas: {result['statistics']}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ ERRO NO PROCESSO DE PALETIZAÇÃO: {e}")
            return {
                'success': False,
                'error': str(e),
                'context': self.context,
                'statistics': {},
                'output_files': {}
            }
        

    def run_from_xml(self, xml_content: Union[bytes, str], filename: Optional[str] = None, config_file: Optional[str] = None, output_dir: Optional[str] = None, validation_file: Optional[str] = None) -> Dict[str, Any]:
        """Entrypoint for endpoint: saves XML to `data/xml_in` and triggers palletization.

        - `xml_content`: bytes or text of the XML sent by the endpoint.
        - `filename`: optional filename to use when saving. If omitted a timestamped name is created.
        - `config_file`: path to config.json; if omitted, attempts to use `data/config.json`.
        - `output_dir` and `validation_file` are forwarded to the pipeline.
        """
        
        saved = self.save_xml_input(xml_content, filename=filename)

        base_dir = Path(__file__).parent.parent / 'data'
        config_file = base_dir / 'config.json'
        input_file = base_dir / 'input.json'
        validacao_file = base_dir / 'output.json'
        output_dir = base_dir 

        try:
            self.gerar_arquivos_jsons(saved_path=str(saved), input_file=str(input_file), config_file=config_file)
        except Exception as e:
            self.logger.error(f"Erro ao executar o Converter: {e}")
            raise e
        try:
            result = self.execute_palletization(config_file=str(config_file), data_file=str(input_file), output_dir=str(output_dir), validation_file=str(validacao_file))
        except Exception as e:
            self.logger.error(f"Erro ao executar palletization a partir do XML salvo: {e}")
            raise e
        
        # save logger file into the same output directory used for palletization
        try:
            map_number = None
            try:
                ctx = result.get('context')
                map_number = getattr(ctx, 'MapNumber', None)
            except Exception:
                map_number = None

            if map_number:
                dest = Path(output_dir) / f'process_log_map_{map_number}.json'
                resultado = logger.save(str(dest))
            else:
                resultado = logger.save(output_dir)
        except Exception:
            resultado = logger.save()

        return result

if __name__ == "__main__":
    #python -m rules.run_rules_palletizing
    paletizador = PalletizingProcessor(debug_enabled=True)
    result = paletizador.run()
    print(result)
