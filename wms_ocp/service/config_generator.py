"""
Gerador de Arquivos de Configuração

Este módulo é responsável por extrair e gerar os arquivos de configuração (config.json)
a partir dos dados de entrada do sistema de paletização.

O arquivo de configuração contém:
- Settings: Configurações globais do mapa (ex: maxPalletHeight, CombinedGroups, etc)
- MapNumber: Número identificador do mapa
- NotPalletizedItems: Lista de itens que não devem ser paletizados
- Type: Tipo do contexto (Rota, AS, Mixed, CrossDocking, T4)

Inclui lógica de:
- DE/PARA de códigos de warehouse
- Carregamento de configurações de CSV (WarehouseConfiguration.csv)
- Mapeamento de nomes de colunas para Settings
- Conversão de valores (0/1 para True/False)
- Carregamento de CombinedGroups de tabelas relacionadas
"""

import json
import csv
from pathlib import Path
from typing import Dict, Any, Optional, Union
import logging
from datetime import datetime
from ..domain.rule_configuration import build_settings_for_unb_code

logger = logging.getLogger(__name__)

# DE/PARA de códigos de warehouse (normalização de códigos antigos)
WAREHOUSE_DEPARA = {
    '232': '771',   # 232 -> 771
    '916': '764',   # 916 -> 764
    '549': '71',    # 549 -> 71
    '550': '538',   # 550 -> 538
    '646': '575',   # 646 -> 575
    '910': '724',   # 910 -> 724
    '626': '539',
    '634':'216'
}

# Códigos a ignorar (não existem mais / outro sistema)
IGNORE_WAREHOUSE_CODES = {'57059', 'PY1n', 'PY1l', 'PY14', 'BR6V', 'BRV3A', 'BR53', 'BRV1', '015'}


class ConfigGenerator:
    """
    Gera arquivos de configuração a partir de dados de entrada
    
    Suporta duas fontes de dados:
    1. JSON de entrada (extração simples)
    2. CSV de configurações de warehouse (carregamento completo com DE/PARA)
    """
    
    def __init__(self, database_path: Optional[Path] = None):
        """
        Args:
            database_path: Caminho para o diretório 'database' com os CSVs
                          Se None, usa Path(__file__).parent.parent / 'database'
        """
        self.logger = logging.getLogger(__name__)
        
        # Define caminho padrão do banco de dados
        if database_path is None:
            self.database_path = Path(__file__).parent.parent / 'database'
        else:
            self.database_path = Path(database_path)
    
    def apply_warehouse_depara(self, unb_code: str) -> Optional[str]:
        """
        Aplica DE/PARA para corrigir códigos de armazém
        
        Args:
            unb_code: Código original do armazém
            
        Returns:
            Código corrigido (ou None se deve ser ignorado)
        """
        if unb_code in IGNORE_WAREHOUSE_CODES:
            self.logger.warning(f"UnbCode {unb_code} será ignorado (não existe mais / outro sistema)")
            return None
        
        if unb_code in WAREHOUSE_DEPARA:
            corrected = WAREHOUSE_DEPARA[unb_code]
            self.logger.info(f"UnbCode {unb_code} → {corrected} (DE/PARA aplicado)")
            return corrected
        
        return unb_code
    
    def load_combined_groups(self, warehouse_id: int) -> str:
        """
        Carrega CombinedGroups das tabelas GroupCombination e GroupCombinationGroup
        
        Args:
            warehouse_id: ID do warehouse
            
        Returns:
            String formatada como: "(10, 20, 50, 90, 100, 200); (30, 40, 60, 70, 80)"
        """
        try:
            # Carrega GroupCombination - encontra combinações para este warehouse
            group_comb_file = self.database_path / 'GroupCombination.csv'
            
            if not group_comb_file.exists():
                self.logger.warning(f"Arquivo não encontrado: {group_comb_file}, usando default")
                return "(10, 20, 50, 90, 100, 200); (30, 40, 60, 70, 80)"
            
            combination_ids = []
            
            with open(group_comb_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    wh_id = (row.get('WarehouseId') or '').strip()
                    is_global = (row.get('IsGlobal') or '0').strip() == '1'
                    active = (row.get('Active') or '0').strip() == '1'
                    
                    if active and (wh_id == str(warehouse_id) or (is_global and not wh_id)):
                        combination_ids.append(row.get('Id'))
            
            if not combination_ids:
                self.logger.info("Nenhuma combinação encontrada, usando default")
                return "(10, 20, 50, 90, 100, 200); (30, 40, 60, 70, 80)"
            
            # Carrega GroupCombinationGroup - pega grupos para cada combinação
            group_comb_group_file = self.database_path / 'GroupCombinationGroup.csv'
            
            if not group_comb_group_file.exists():
                self.logger.warning(f"Arquivo não encontrado: {group_comb_group_file}, usando default")
                return "(10, 20, 50, 90, 100, 200); (30, 40, 60, 70, 80)"
            
            combinations = {}
            
            with open(group_comb_group_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    comb_id = (row.get('GroupCombinationId') or '').strip()
                    if comb_id in combination_ids:
                        group_code = (row.get('GroupCode') or '').strip()
                        if comb_id not in combinations:
                            combinations[comb_id] = []
                        if group_code:
                            combinations[comb_id].append(int(group_code))
            
            # Formata como string: cada combinação entre parênteses, separadas por ponto-e-vírgula
            formatted_groups = []
            for comb_id, groups in combinations.items():
                sorted_groups = sorted(groups)
                formatted_groups.append(f"({', '.join(map(str, sorted_groups))})")
            
            result = "; ".join(formatted_groups) if formatted_groups else "(10, 20, 50, 90, 100, 200); (30, 40, 60, 70, 80)"
            self.logger.info(f"CombinedGroups carregados: {result}")
            return result
        
        except Exception as e:
            self.logger.error(f"Erro ao carregar CombinedGroups: {e}")
            return "(10, 20, 50, 90, 100, 200); (30, 40, 60, 70, 80)"
    
    def load_warehouse_config_from_csv(
        self,
        unb_code: str,
        delivery_date: Optional[str] = None,
        map_type: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Carrega configurações completas do warehouse a partir dos CSVs
        
        Esta função implementa a lógica crucial do stackbuilder:
        - Aplica DE/PARA de códigos
        - Carrega do WarehouseConfiguration.csv
        - Faz mapeamento de colunas CSV para nomes de Settings
        - Converte valores (0/1 para True/False)
        - Carrega CombinedGroups de tabelas relacionadas
        - Aplica overrides baseados em data
        
        Args:
            unb_code: Código do warehouse (será normalizado via DE/PARA)
            delivery_date: Data de entrega (para overrides específicos)
            
        Returns:
            Dict com Settings completas
        """
        self.logger.info(f"Carregando configuração do warehouse: {unb_code}")
        
        # Aplica DE/PARA antes de buscar no CSV
        original_unb = unb_code
        unb_code = self.apply_warehouse_depara(unb_code)
        
        if unb_code is None:
            self.logger.warning(f"Warehouse {original_unb} não será processado (código ignorado)")
            return self._get_default_settings()
        
        # Settings padrão
        default_settings = self._get_default_settings()
        
        try:
            # Primeiro, busca WarehouseId a partir do UnbCode (APÓS DE/PARA)
            warehouse_file = self.database_path / 'Warehouse.csv'
            warehouse_id = None
            
            if warehouse_file.exists():
                with open(warehouse_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('UnbCode') == unb_code:
                            warehouse_id = int(row.get('Id', 0))
                            self.logger.info(f"WarehouseId={warehouse_id} encontrado para UnbCode={unb_code}")
                            break
            
            if warehouse_id is None:
                self.logger.warning(f"UnbCode {unb_code} não encontrado em Warehouse.csv (usando defaults)")
            
            # Carrega configurações do WarehouseConfiguration.csv
            warehouse_config_file = self.database_path / 'WarehouseConfiguration.csv'
            
            if not warehouse_config_file.exists():
                self.logger.warning(f"Arquivo não encontrado: {warehouse_config_file}")
                return default_settings
            
            with open(warehouse_config_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('UnbCode') == unb_code:
                        settings = default_settings.copy()
                        
                        # Mapeia colunas CSV para Settings (DE/PARA de nomes)
                        settings["EnableSafeSideRule"] = "True" if row.get('EnableSafeSideRule') == '1' else "False"
                        settings["UseBaySmallerThan35"] = "True" if row.get('UseBayLessThan35') == '1' else "False"
                        settings["KegExclusivePallet"] = "True" if row.get('KegExclusivePallet') == '1' else "False"
                        settings["IncludeTopOfPallet"] = "True" if row.get('IncludeTopOfPallet') == '1' else "False"
                        settings["MinimumOccupationPercentage"] = str(row.get('MinimumPercentageOccupancy', '0'))
                        settings["AllowEmptySpaces"] = "True" if row.get('AllowEmptyBays') == '1' else "False"
                        settings["AllowVehicleWithoutBays"] = "True" if row.get('AllowVehicleWithoutBays') == '1' else "False"
                        settings["DistributeItemsOnEmptySpaces"] = "True" if row.get('DistributeItemsOnEmptyPallets') == '1' else "False"
                        settings["MinimumQuantityOfSKUsToDistributeOnEmptySpaces"] = str(row.get('MinimumQuantityOfSKUsToDistributeOnEmptyPallets', '0'))
                        settings["AdjustReassemblesAfterWater"] = "True" if row.get('AdjustReassemblesAfterWater') == '1' else "False"
                        settings["JoinDisposableContainers"] = "True" if row.get('JoinDisposables') == '1' else "False"
                        settings["OccupationToJoinMountedSpaces"] = str(row.get('JoinPalletsWithLessThanOccupancy', '0'))
                        settings["OrderByItemsSequence"] = "True" if row.get('OrderByItemsSequence') == '1' else "False"
                        settings["OrderPalletByProductGroup"] = "True" if row.get('OrderPalletByProductGroup') == '1' else "False"
                        settings["OrderProductsForAutoServiceMap"] = "True" if row.get('OrderProductsForAutoServiceMap') == '1' else "False"
                        settings["DistributeMixedRouteOnASCalculus"] = "True" if row.get('DistributeMixedRouteOnASCalculus') == '1' else "False"
                        settings["GroupComplexLoads"] = "True" if row.get('AllowGroupingComplexLoads') == '1' else "False"
                        settings["MinimumVolumeInComplexLoads"] = str(row.get('MinimumVolumeInComplexLoads', '42'))
                        settings["QuantitySkuInComplexLoads"] = str(row.get('QuantitySkuInComplexLoads', '30'))
                        settings["UseItemsExclusiveOfWarehouse"] = "True" if row.get('UseItemsExclusiveOfWarehouse') == '1' else "False"
                        
                        # # CombinedGroups - carrega das tabelas relacionadas
                        # if warehouse_id:
                        #     settings["CombinedGroups"] = self.load_combined_groups(warehouse_id)
                        # else:
                        #     self.logger.warning("Usando default CombinedGroups (WarehouseId não encontrado)")
                        
                        result = build_settings_for_unb_code(unb_code, map_type=map_type)

                        settings["EnableSafeSideRule"] = str(
                            result.get("EnableSafeSideRule", "True" if row.get('EnableSafeSideRule') == '1' else "False")
                        )
                        settings["UseBaySmallerThan35"] = str(
                            result.get("UseBaySmallerThan35", "True" if row.get('UseBayLessThan35') == '1' else "False")
                        )
                        settings["KegExclusivePallet"] = str(
                            result.get("kegExclusivePallet", "True" if row.get('KegExclusivePallet') == '1' else "False")
                        )
                        settings["IncludeTopOfPallet"] = str(
                            result.get("includeTopOfPallet", "True" if row.get('IncludeTopOfPallet') == '1' else "False")
                        )
                        settings["MinimumOccupationPercentage"] = str(## nao tem no rule confg
                            result.get("MinimumOccupationPercentage", str(row.get('MinimumPercentageOccupancy', '0')))
                        )
                        settings["AllowEmptySpaces"] = str(
                            result.get("allowEmptyBays", "True" if row.get('AllowEmptyBays') == '1' else "False")
                        )
                        settings["AllowVehicleWithoutBays"] = str(
                            result.get("allowVehicleWithoutBays", "True" if row.get('AllowVehicleWithoutBays') == '1' else "False")
                        )

                        settings["DistributeItemsOnEmptySpaces"] =str(
                            result.get("distributeItemsOnEmptyPallets", "True" if row.get('DistributeItemsOnEmptyPallets') == '1' else "False")
                        )
                        settings["MinimumQuantityOfSKUsToDistributeOnEmptySpaces"] = str(
                            result.get("MinimumQuantityOfSKUsToDistributeOnEmptySpaces", str(row.get('MinimumQuantityOfSKUsToDistributeOnEmptyPallets', '0')))
                        )
                        settings["AdjustReassemblesAfterWater"] = str(
                            result.get("adjustReassemblesAfterWater", "True" if row.get('AdjustReassemblesAfterWater') == '1' else "False")
                        )
                        settings["JoinDisposableContainers"] = str(
                            result.get("JoinDisposableContainers", "True" if row.get('JoinDisposables') == '1' else "False")
                        )
                        settings["OccupationToJoinMountedSpaces"] = str(
                            result.get("OccupationToJoinMountedSpaces", str(row.get('JoinPalletsWithLessThanOccupancy', '0')))
                        )
                        settings["OrderByItemsSequence"] = str(
                            result.get("OrderByItemsSequence", "True" if row.get('OrderByItemsSequence') == '1' else "False")
                        )
                        settings["OrderPalletByProductGroup"] = str(
                            result.get("OrderPalletByProductGroup", "True" if row.get('OrderPalletByProductGroup') == '1' else "False")
                        )
                        settings["OrderProductsForAutoServiceMap"] = str(
                            result.get("OrderProductsForAutoServiceMap", "True" if row.get('OrderProductsForAutoServiceMap') == '1' else "False")
                        )
                        settings["DistributeMixedRouteOnASCalculus"] = str(
                            result.get("distributeMixedRouteOnASCalculus", "True" if row.get('DistributeMixedRouteOnASCalculus') == '1' else "False" )
                        )
                        settings["GroupComplexLoads"] = str(
                            result.get("allowGroupingComplexLoads", "True" if row.get('AllowGroupingComplexLoads') == '1' else "False")
                        )
                        settings["MinimumVolumeInComplexLoads"] = str(
                            result.get("MinimumVolumeInComplexLoads", str(row.get('MinimumVolumeInComplexLoads', '42')))
                        )
                        settings["QuantitySkuInComplexLoads"] = str(
                            result.get("QuantitySkuInComplexLoads", str(row.get('QuantitySkuInComplexLoads', '30')))
                        )
                        settings["UseItemsExclusiveOfWarehouse"] = str(
                            result.get("UseItemsExclusiveOfWarehouse", "True" if row.get('UseItemsExclusiveOfWarehouse') == '1' else "False")
                        )
                        settings["OrderPalletByPackageCodeOccupation"] = str(
                            result.get("OrderPalletByPackageCodeOccupation", settings.get("OrderPalletByPackageCodeOccupation"))
                        )
                        settings["OrderPalletByCancha"] = str(
                            result.get("OrderPalletByCancha", settings.get("OrderPalletByCancha"))
                        )
                        settings["LimitPackageGroups"] = str(
                            result.get("LimitPackageGroups", settings.get("LimitPackageGroups"))
                        )
                        settings["BulkAllPallets"] = str(
                            result.get("bulkAllPallets", settings.get("BulkAllPallets"))
                        )
                        settings["NotMountBulkPallets"] = str(
                            result.get("notMountBulkPallets", settings.get("NotMountBulkPallets"))
                        )
                        settings["ReturnableAndDisposableSplitRuleDisabled"] = str(
                            result.get(
                                "returnableAndDisposableSplitRuleDisabled",
                                settings.get("ReturnableAndDisposableSplitRuleDisabled"),
                            )
                        )
                        settings["IsotonicTopPalletCustomOrderRule"] = str(
                            result.get(
                                "isotonicTopPalletCustomOrderRule",
                                settings.get("IsotonicTopPalletCustomOrderRule"),
                            )
                        )
                        settings["ReassignmentOfNonPalletizedItems"] = str(
                            result.get(
                                "reassignmentOfNonPalletizedItems",
                                settings.get("ReassignmentOfNonPalletizedItems"),
                            )
                        )
                        settings["SideBalanceRule"] = str(
                            result.get("sideBalanceRule", settings.get("SideBalanceRule", "True"))
                        )
                        settings["PalletizeDetached"] = str(
                            result.get("PalletizeDetached", settings.get("PalletizeDetached"))
                        )
                        settings["MaxPackageGroups"] = str(
                            result.get("MaxPackageGroups", settings.get("MaxPackageGroups"))
                        )
                        settings["OrderPalletByGroupSubGroupAndPackagingItem"] = str(
                            result.get(
                                "orderPalletByGroupSubGroupAndPackagingItem",
                                settings.get("OrderPalletByGroupSubGroupAndPackagingItem"),
                            )
                        )
                        settings["ShouldLimitPackageGroups"] = str(
                            result.get("LimitPackageGroups", settings.get("ShouldLimitPackageGroups"))
                        )
                        settings["ProductGroupSpecific"] = str(
                            result.get("productGroupSpecific", settings.get("ProductGroupSpecific"))
                        )
                        settings["PalletEqualizationRule"] = str(
                            result.get(
                                "PalletEqualizationRule",
                                settings.get("PalletEqualizationRule"),
                            )
                        )
                        settings["OccupationToJoinMountedSpaces"] = str(
                                result.get(
                                    "OccupationToJoinMountedSpaces",
                                    settings.get("OccupationToJoinMountedSpaces"),
                                )
                            )
                        
                        # OVERRIDE BASEADO EM DATA: Warehouse 916→764 mudou config em 02/dez/2025
                        if unb_code == '764' and delivery_date:
                            try:
                                # Parse delivery date (pode vir com timezone)
                                date_str = delivery_date.split('T')[0]  # Get YYYY-MM-DD
                                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                                
                                # CUTOFF: 02/dez/2025 - mudança de configuração (>= 02/dez usa 29)
                                cutoff_date = datetime(2025, 12, 2)
                                
                                if date_obj >= cutoff_date:
                                    self.logger.info(f"Override: Data {date_obj.date()} >= 02/dez/2025, OccupationToJoinMountedSpaces: {settings['OccupationToJoinMountedSpaces']} → 29")
                                    settings["OccupationToJoinMountedSpaces"] = "22"
                                else:
                                    self.logger.info(f"Data {date_obj.date()} < 02/dez/2025, mantendo OccupationToJoinMountedSpaces = {settings['OccupationToJoinMountedSpaces']}")
                            except Exception as e:
                                self.logger.error(f"Erro ao processar data '{delivery_date}': {e}")
                        
                        self.logger.info(f"✓ Config carregada para UnbCode={unb_code} (original={original_unb})")
                        return settings
            
            self.logger.warning(f"Config não encontrada para UnbCode={unb_code}, usando defaults")
            return default_settings
            
        except Exception as e:
            self.logger.error(f"Erro ao carregar warehouse config: {e}")
            import traceback
            traceback.print_exc()
            return default_settings
    
    def _get_default_settings(self) -> Dict[str, Any]:
        """Retorna configurações padrão"""
        return {
            "UseBaySmallerThan35": "False",
            "KegExclusivePallet": "False",
            "IncludeTopOfPallet": "True",
            "MinimumOccupationPercentage": "0",
            "AllowEmptySpaces": "False",
            "AllowVehicleWithoutBays": "False",
            "DistributeItemsOnEmptySpaces": "False",
            "MinimumQuantityOfSKUsToDistributeOnEmptySpaces": "0",
            "AdjustReassemblesAfterWater": "False",
            "JoinDisposableContainers": "False",
            "OccupationToJoinMountedSpaces": "0",
            "OrderByItemsSequence": "False",
            "OrderPalletByProductGroup": "False",
            "OrderProductsForAutoServiceMap": "False",
            "DistributeMixedRouteOnASCalculus": "False",
            "OrderPalletByPackageCodeOccupation": "True",
            "OrderPalletByCancha": "True",
            "GroupComplexLoads": "True",
            "LimitPackageGroups": "True",
            "CombinedGroups": "(10, 20, 50, 90, 100, 200); (30, 40, 60, 70, 80)",
            "MinimumVolumeInComplexLoads": "42",
            "QuantitySkuInComplexLoads": "30",
            "UseItemsExclusiveOfWarehouse": "False",
            "EnableSafeSideRule": "False",
            "BulkAllPallets": "False",
            "NotMountBulkPallets": "True",
            "ReturnableAndDisposableSplitRuleDisabled": "True",
            "IsotonicTopPalletCustomOrderRule": "True",
            "ReassignmentOfNonPalletizedItems": "True",
            "SideBalanceRule": "True",
            "ReduceVolumePallets": "False",
            "PercentageReductionInPalletOccupancy": "0",
            "QuantityOfPackagingOnSamePallet": "0",
            "LoadControlEnabled": "False",
            "DebugStackBuilderEnabled": "False",
            "PalletizeDetached": "True",
            "MaxPackageGroups": "6",
            "OrderPalletByGroupSubGroupAndPackagingItem": "True",
            "ShouldLimitPackageGroups": "True",
            "OccupationAdjustmentToPreventExcessHeight": "False",
            "PalletEqualizationRule": "False",
            "ProductGroupSpecific": "",
            "PercentOccupationMinByDivision": "0",
            "PercentOccupationMinBySelectionPalletDisassembly": "0"
        }
    
    def extract_config_from_input(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extrai as configurações do JSON de entrada
        
        Args:
            input_data: Dados do arquivo JSON de entrada (JsonEntradaStackBuilder.json)
            
        Returns:
            Dict com as configurações extraídas (Settings, MapNumber, NotPalletizedItems, Type)
        """
        self.logger.info("Extraindo configurações do JSON de entrada...")
        
        config = {
            "Settings": {},
            "MapNumber": None,
            "NotPalletizedItems": [],
            "Type": None
        }
        
        # 1. Extrai Settings
        if "Settings" in input_data:
            config["Settings"] = input_data["Settings"]
            self.logger.info(f"✓ Settings encontradas: {len(config['Settings'])} configurações")
        elif "settings" in input_data:
            config["Settings"] = input_data["settings"]
            self.logger.info(f"✓ Settings encontradas: {len(config['Settings'])} configurações")
        else:
            # Tenta extrair de outros lugares comuns
            config["Settings"] = self._extract_settings_from_data(input_data)
            self.logger.info(f"✓ Settings extraídas: {len(config['Settings'])} configurações")
        
        # 2. Extrai MapNumber
        config["MapNumber"] = self._extract_map_number(input_data)
        self.logger.info(f"✓ MapNumber: {config['MapNumber']}")
        
        # 3. Extrai NotPalletizedItems
        config["NotPalletizedItems"] = self._extract_not_palletized_items(input_data)
        self.logger.info(f"✓ NotPalletizedItems: {len(config['NotPalletizedItems'])} itens")
        
        # 4. Extrai Type
        config["Type"] = self._extract_type(input_data)
        self.logger.info(f"✓ Type: {config['Type']}")
        
        return config
    
    def _extract_settings_from_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extrai configurações de lugares alternativos no JSON
        """
        settings = {}
        
        # Procura em diferentes locais possíveis
        possible_keys = [
            "Configuration", "Config", "Configuracao",
            "PalletSettings", "PalletConfiguration"
        ]
        
        for key in possible_keys:
            if key in data and isinstance(data[key], dict):
                settings.update(data[key])
        
        # Configurações comuns que podem estar no root
        common_settings = [
            "MaxPalletHeight", "maxPalletHeight",
            "CombinedGroups", "combinedGroups",
            "PalletType", "palletType",
            "AllowRotation", "allowRotation",
            "MaxWeight", "maxWeight"
        ]
        
        for key in common_settings:
            if key in data:
                settings[key] = data[key]
        
        # Aplica conversões (de-para) nas settings extraídas
        settings = self._convert_and_normalize_settings(settings)
        
        return settings
    
    def _convert_and_normalize_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converte e normaliza os valores das settings (de-para)
        
        Faz as conversões:
        - Strings boolean ("true", "false") -> bool
        - Strings numéricas -> int ou float (aceita vírgula como separador decimal)
        """
        converted = {}
        
        for key, value in settings.items():
            # Converte booleanos em string para bool
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in ('true', 'false'):
                    converted[key] = (normalized == 'true')
                    continue
            
            # Converte strings numéricas
            if isinstance(value, str):
                s = value.strip()
                if s == '':
                    converted[key] = value
                    continue
                
                # Ignora booleanos já tratados
                if s.lower() in ('true', 'false'):
                    converted[key] = (s.lower() == 'true')
                    continue
                
                # Tenta int
                try:
                    if s.lstrip('+-').isdigit():
                        converted[key] = int(s)
                        continue
                except Exception:
                    pass
                
                # Tenta float (aceita vírgula como decimal)
                try:
                    normalized_num = s.replace(',', '.')
                    f = float(normalized_num)
                    converted[key] = f
                    continue
                except Exception:
                    pass
            
            # Mantém valor original se não foi convertido
            converted[key] = value
        
        return converted
    
    def _extract_map_number(self, data: Dict[str, Any]) -> Optional[Union[int, str]]:
        """
        Extrai o MapNumber de diferentes locais possíveis
        """
        # Lista de possíveis chaves onde o MapNumber pode estar
        possible_keys = [
            "MapNumber", "mapNumber", "map_number",
            "Number", "number", "Id", "id",
            "DocumentNumber", "documentNumber"
        ]
        
        for key in possible_keys:
            if key in data and data[key] is not None:
                try:
                    return int(data[key])
                except (ValueError, TypeError):
                    return str(data[key])
        
        # Tenta extrair do Request block
        request = data.get("Request", {})
        if isinstance(request, dict):
            for key in possible_keys:
                if key in request and request[key] is not None:
                    try:
                        return int(request[key])
                    except (ValueError, TypeError):
                        return str(request[key])
        
        return None
    
    def _extract_not_palletized_items(self, data: Dict[str, Any]) -> list:
        """
        Extrai lista de itens não paletizados
        """
        possible_keys = [
            "NotPalletizedItems", "notPalletizedItems", "not_palletized_items",
            "NonPalletizedItems", "nonPalletizedItems",
            "ExcludedItems", "excludedItems"
        ]
        
        for key in possible_keys:
            if key in data and isinstance(data[key], list):
                return data[key]
        
        return []
    
    def _extract_unb_code(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Extrai o código do warehouse (UnbCode/SupportPoint) do JSON
        Remove zeros à esquerda para normalizar (00916 -> 916)
        """
        def normalize_code(code: str) -> str:
            """Remove - e zeros à esquerda"""
            code = code.replace("-", "").strip()
            try:
                # Converte para int e volta para string (remove zeros à esquerda)
                return str(int(code))
            except ValueError:
                return code
        
        # Tenta em diferentes locais possíveis

        unbCode = data.get("Warehouse", {}).get("UnbCode", None)

        if unbCode:
            return normalize_code(str(unbCode))
    
        # 1. Campo direto UnbCode
        if "UnbCode" in data:
            return normalize_code(str(data["UnbCode"]))
        
        # 2. SupportPoint (formato: -00916)
        if "SupportPoint" in data:
            return normalize_code(str(data["SupportPoint"]))
        
        # 3. Dentro de Orders[0].Cross.SupportPoint
        orders = data.get("Orders", [])
        if orders and isinstance(orders, list) and len(orders) > 0:
            cross = orders[0].get("Cross", {})
            if "SupportPoint" in cross:
                return normalize_code(str(cross["SupportPoint"]))
        
        # 4. Warehouse
        if "Warehouse" in data:
            warehouse = data["Warehouse"]
            if isinstance(warehouse, dict):
                if "UnbCode" in warehouse:
                    return normalize_code(str(warehouse["UnbCode"]))
                if "Code" in warehouse:
                    return normalize_code(str(warehouse["Code"]))
            else:
                return normalize_code(str(warehouse))
        
        return None
    
    def _extract_type(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Extrai o tipo do mapa/contexto
        """
        # Tipo explícito
        if "Type" in data:
            return self._normalize_type(data["Type"])
        if "type" in data:
            return self._normalize_type(data["type"])
        
        # Tenta do DocumentType
        if "DocumentType" in data:
            return self._normalize_type(data["DocumentType"])
        if "documentType" in data:
            return self._normalize_type(data["documentType"])
        
        # Tenta do Request
        request = data.get("Request", {})
        if isinstance(request, dict):
            if "mapType" in request:
                return self._normalize_type(request["mapType"])
            if "MapType" in request:
                return self._normalize_type(request["MapType"])
        
        return None
    
    def _normalize_type(self, type_value: Any) -> str:
        """
        Normaliza o valor do tipo para um formato consistente
        """
        if type_value is None:
            return None
        
        # Se for número, converte para nome
        if isinstance(type_value, (int, float)):
            type_map = {
                1: "Route",
                2: "AS",
                3: "CrossDocking",
                4: "Mixed",
                5: "T4"
            }
            return type_map.get(int(type_value), "Route")
        
        # Se for string, normaliza
        type_str = str(type_value).lower()
        
        type_aliases = {
            "route": "Route",
            "rota": "Route",
            "as": "AS",
            "armazenagem": "AS",
            "mixed": "Mixed",
            "mista": "Mixed",
            "mixta": "Mixed",
            "crossdocking": "CrossDocking",
            "cross-docking": "CrossDocking",
            "cross_docking": "CrossDocking",
            "t4": "T4"
        }
        
        return type_aliases.get(type_str, "Route")
    
    def generate_config_file(
        self,
        input_file: Union[str, Path],
        output_file: Optional[Union[str, Path]] = None,
        overwrite: bool = False
    ) -> Path:
        """
        Gera arquivo de configuração a partir de um arquivo de entrada
        
        Args:
            input_file: Caminho do arquivo JSON de entrada
            output_file: Caminho do arquivo de saída (opcional, será gerado automaticamente)
            overwrite: Se True, sobrescreve arquivo existente
            
        Returns:
            Path do arquivo de configuração gerado
        """
        input_path = Path(input_file)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Arquivo de entrada não encontrado: {input_file}")
        
        self.logger.info(f"Lendo arquivo de entrada: {input_path.name}")
        
        # Lê arquivo de entrada
        with open(input_path, 'r', encoding='utf-8') as f:
            input_data = json.load(f)
        
        # Extrai configurações
        config = self.extract_config_from_input(input_data)
        
        # Se Settings estiver vazio, tenta carregar do CSV
        if not config["Settings"]:
            self.logger.info("Settings vazia no JSON, tentando carregar do database...")
            
            # Extrai UnbCode/SupportPoint do JSON
            unb_code = self._extract_unb_code(input_data)
            delivery_date = input_data.get("DeliveryDate")
            
            if unb_code:
                unb_code = self.apply_warehouse_depara(unb_code)
                self.logger.info(f"UnbCode encontrado: {unb_code}")
                # Map kind string to numeric MapType used in ruleconfiguration CSV
                kind_to_map_type = {"Route": 1, "AS": 2, "CrossDocking": 3, "Mixed": 4, "T4": 5}
                numeric_map_type = kind_to_map_type.get(config.get("Type"), None)
                config["Settings"] = self.load_warehouse_config_from_csv(unb_code, delivery_date, map_type=numeric_map_type)
                # config["Settings_Nonv"] = build_settings_for_unb_code(unb_code)
            else:
                self.logger.warning("UnbCode não encontrado no JSON, usando Settings padrão")
                config["Settings"] = self._get_default_settings()
        
        # Define nome do arquivo de saída
        if output_file is None:
            # Gera nome automático baseado no input
            # Ex: JsonEntradaStackBuilder.json -> config_JsonEntradaStackBuilder.json
            output_file = input_path.parent / f"config_{input_path.stem}.json"
            
            # Ou usa o MapNumber se disponível
            if config["MapNumber"]:
                output_file = input_path.parent / f"config_map_{config['MapNumber']}.json"
        
        output_path = Path(output_file)
        
        # Verifica se já existe
        if output_path.exists() and not overwrite:
            self.logger.warning(f"Arquivo já existe: {output_path}")
            self.logger.warning("Use overwrite=True para sobrescrever")
            return output_path
        
        # Salva arquivo de configuração
        self.logger.info(f"Gerando arquivo de configuração: {output_path.name}")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"✓ Arquivo de configuração gerado: {output_path}")
        self.logger.info(f"  - Settings: {len(config['Settings'])} configurações")
        self.logger.info(f"  - MapNumber: {config['MapNumber']}")
        self.logger.info(f"  - NotPalletizedItems: {len(config['NotPalletizedItems'])} itens")
        self.logger.info(f"  - Type: {config['Type']}")
        
        return output_path
    
    def update_config_file(
        self,
        config_file: Union[str, Path],
        updates: Dict[str, Any]
    ) -> Path:
        """
        Atualiza um arquivo de configuração existente
        
        Args:
            config_file: Caminho do arquivo de configuração
            updates: Dicionário com atualizações a serem aplicadas
            
        Returns:
            Path do arquivo atualizado
        """
        config_path = Path(config_file)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Arquivo de configuração não encontrado: {config_file}")
        
        # Lê config atual
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Aplica atualizações
        for key, value in updates.items():
            if key == "Settings" and isinstance(value, dict):
                # Atualiza settings existentes sem remover as antigas
                config["Settings"].update(value)
            else:
                config[key] = value
        
        # Salva
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"✓ Arquivo de configuração atualizado: {config_path}")
        
        return config_path


def generate_config_from_input(
    input_file: Union[str, Path],
    output_file: Optional[Union[str, Path]] = None,
    overwrite: bool = False
) -> Path:
    """
    Função helper para gerar config rapidamente
    
    Args:
        input_file: Arquivo JSON de entrada
        output_file: Arquivo de saída (opcional)
        overwrite: Sobrescrever se existir
        
    Returns:
        Path do arquivo gerado
    """
    generator = ConfigGenerator()
    return generator.generate_config_file(input_file, output_file, overwrite)


# Exemplo de uso
if __name__ == "__main__":
    import sys
    
    # Configura logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    if len(sys.argv) < 2:
        print("Uso: python config_generator.py <arquivo_entrada.json> [arquivo_saida.json]")
        print()
        print("Exemplos:")
        print("  python config_generator.py JsonEntradaStackBuilder.json")
        print("  python config_generator.py data/input.json data/config.json")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        result = generate_config_from_input(input_file, output_file, overwrite=True)
        print(f"\n✓ Sucesso! Arquivo gerado: {result}")
    except Exception as e:
        print(f"\n✗ Erro: {e}")
        sys.exit(1)
