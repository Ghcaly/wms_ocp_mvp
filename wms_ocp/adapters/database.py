from ast import List
from typing import Optional
import pandas as pd
import math
import re
from pathlib import Path

from ..domain.packing_group import PackingGroup
from ..domain.pallet_setting import PalletSetting
from ..domain.factor import Factor
from ..domain.product import BoxTemplate, Product, Chopp, Returnable, IsotonicWater, DisposableProduct, Package
from ..domain.container_type import ContainerType
from ..domain.item_marketplace import ItemMarketplace

# Cache global para produtos marketplace
_marketplace_skus_cache = None

def buscar_item(df, sku_code, UnbCode=None):
        """Busca o item no DataFrame pelo código."""

        code = str(sku_code)
        row_data = df.loc[code] 

        if isinstance(row_data, pd.DataFrame):
            if UnbCode is not None:
                result = row_data[(row_data['Código Unb'] == UnbCode) | (row_data['Código Unb'] == str(UnbCode))]
                if result is not None and len(result) > 0:
                    return result.iloc[0]
                
            if len(row_data) > 1:
                row_data = row_data[(row_data['Código Unb'] == 'None') | (row_data['Código Unb'] == 'nan')]
                print(len(row_data))
                return row_data.iloc[0]
            elif len(row_data) == 1:
                return row_data.iloc[0]
            else:
                return row_data.iloc[0]

        return row_data

def load_marketplace_skus():
    """Carrega lista de SKUs marketplace do CSV uma única vez"""
    global _marketplace_skus_cache
    
    if _marketplace_skus_cache is not None:
        return _marketplace_skus_cache
    
    try:
        # Tenta diferentes caminhos
        csv_paths = [
            "/mnt/c/prd_debian/data 2(Export).csv",
            "c:/prd_debian/data 2(Export).csv",
            "/home/prd_debian/data 2(Export).csv",
            Path(__file__).parent.parent.parent / "data 2(Export).csv"
        ]
        
        df = None
        for csv_path in csv_paths:
            try:
                # Tenta diferentes encodings
                for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
                    try:
                        df = pd.read_csv(csv_path, encoding=encoding)
                        print(f"[INFO] CSV marketplace carregado de: {csv_path}")
                        break
                    except (UnicodeDecodeError, FileNotFoundError):
                        continue
                if df is not None:
                    break
            except Exception:
                continue
        
        if df is None:
            print("[AVISO] CSV de marketplace não encontrado, produtos marketplace não serão identificados")
            _marketplace_skus_cache = set()
            return _marketplace_skus_cache
        
        # Filtra apenas produtos com Cluster_Premium = MKTP
        mktp_df = df[df['Cluster_Premium'] == 'MKTP']
        
        # Armazena SKUs como strings
        _marketplace_skus_cache = set(mktp_df['Cod_Produto'].astype(str))
        
        print(f"[INFO] {len(_marketplace_skus_cache)} produtos marketplace carregados do CSV")
        
    except Exception as e:
        print(f"[ERRO] Erro ao carregar CSV marketplace: {e}")
        _marketplace_skus_cache = set()
    
    return _marketplace_skus_cache

def extract_factors_from_row(row):
    """
    Detecta automaticamente todas as colunas do tipo:
    FatorXX e QuantidadeXX
    e cria objetos Factor dinamicamente.
    """
    factors = []
    
    # Garante que row é uma Series e pega os nomes das colunas como strings
    columns = row.index if hasattr(row, 'index') else []
    
    for col in columns:
        # Converte para string caso não seja
        col_str = str(col)
        
        if col_str.startswith("Fator") and not col_str[-1].isdigit():
            continue

        if col_str.startswith("Fator") and any(char.isdigit() for char in col_str):
            size = ''.join(filter(str.isdigit, col_str))

            value = row.get(col, None)
            quantity = row.get(f"Quantidade{size}", None)

            factor_obj = Factor(
                Size=size,
                Value=value,
                Quantity=quantity,
                HasQuantity=not (quantity is None or quantity <= 0)
            )

            factors.append(factor_obj)

    return factors

def extrair_codigo_tipo(descricao: str) -> int:
    """
    Extrai o código do tipo de uma descrição no formato:
    '28 - PET 500 (Tipo: 2 - REFRIGERANTE)'
    
    Returns:
        int: Código do tipo (ex: 2)
    """
    if not descricao:
        return descricao
    
    match = re.search(r'Tipo:\s*(\d+)', descricao)
    if match:
        return int(match.group(1))
    return 0  # ou None, dependendo do comportamento desejado

def create_product(item_dto) -> Product:
    """
    Cria o produto apropriado baseado nos atributos

    Args:
        item_dto: Dados do item

    Returns:
        Instância de Product apropriada
    """
    if getattr(item_dto, 'Barril', False):#Keg
        return Chopp()
    elif getattr(item_dto, 'Retornável', False):#Returnable
        return Returnable()
    elif getattr(item_dto, 'Água/Isotônico', False):
        return IsotonicWater()
    else:
        # Market/Package items have a non-empty Tipo Caixa (e.g. "Garrafeira", "Caixa vazada")
        tipo_caixa = getattr(item_dto, 'Tipo Caixa', None)
        if isinstance(tipo_caixa, str) and tipo_caixa.strip():
            return Package()
        return DisposableProduct()


def parse_combined_groups(raw: Optional[str]):
    """Parse '(10,20); (30,40)' -> [[10,20], [30,40]]"""
    if not raw:
        return []
    groups = []
    for part in raw.split(';'):
        nums = re.findall(r'\d+', part)
        if nums:
            groups.append([int(n) for n in nums])
    return groups

def apply_combined_groups_to_product(product, combined_groups):
    """If a combined group contains product.PackingGroup.GroupCode, set associations."""
    group_code = product.PackingGroup.GroupCode
    for group in combined_groups:
        if group_code in group:
            # faithful to C# — call SetGroupAssociations with the list
            product.SetGroupAssociations(group)
            break
        
def fill_item_from_row(item, combined_groups, support_point, row):
    print(f"[INFO] Enriquecendo item código {item.Code} com dados do DataFrame")
    
    item.Product = create_product(row)
    # item.Product = item.Product or Product()
    # PackingGroup
    item.Product.PackingGroup = PackingGroup(
        Code=row.get('Código embalagem', None),
        PackingCode=row.get('Código tipo embalagem', None),
        PackingName=row.get('Embalagem', None),
        GroupCode=row.get('Grupo', None),
        SubGroupCode=row.get('Subgrupo', None),
        ProductTypeCode=extrair_codigo_tipo(row.get('Embalagem/Tipo produto', "")),
        ProductTypeName=row.get('Nome Catálogo', None),
        IsGlobal=row.get('Ativo', None),
        IsRegional=None,
        WarehouseUnbCode=row.get('Armazém', None),
        WmsId=None,
        CatalogId=row.get('Id Catálogo', None)
    )

    # PalletSetting
    item.Product.PalletSetting = PalletSetting(
        Quantity=row.get('Quantidade Palete', None),
        BulkPriority=row.get('Prioridade Palete', None) if "Prioridade Palete" in row else None,
        QuantityDozen=row.get('Quantidade Palete Dúzia', None),
        QuantityBallast=row.get('Quantidade de Lastros/Camadas', None),
        QuantityBallastMin=row.get('Quantidade Mínima Lastros/Camadas', 0),
        Layers= row.get('Camadas', None),
        IncludeTopOfPallet=row.get('Topo Palete', None),
        BasePallet=row.get('Base palete', None)
    )

    apply_combined_groups_to_product(item.Product, combined_groups)
    
    # Product
    item.Product.Code = item.Code
    item.Product.CodePromax = row.get('Código Unb', None)
    item.Product.Name = row.get('Descrição', None)
    item.Product.GrossWeight = row.get('Peso bruto do item', None)
    item.Product.LayerCode = 0#row.get('Camadas', None)
    item.Product.Factors = extract_factors_from_row(row)
    item.Product.SupportPoint = support_point
    
    # Additional occupation settings (Product properties, not Item)
    item.Product.CalculateAdditionalOccupation = bool(row.get("Ocupação extra", False))
    item.Product.BallastQuantity = int(row.get("Quantidade de Lastros/Camadas", 0) or 0)
    # Note: TotalAreaOccupiedByUnit and TotalAreaOccupiedByBallast need column names from your database
    # item.Product.TotalAreaOccupiedByUnit = row.get("Área total ocupada por unidade", 0) or 0
    # item.Product.TotalAreaOccupiedByBallast = row.get("Área total ocupada por lastro", 0) or 0

    # Item fields
    # item.Amount = None
    item.UnitAmount = row.get("Quantidade de unidades por caixa", None)
    item.factor = row.get("Fator", None)

    raw_box_type = row.get("Tipo Caixa", None)
    raw_units_per_box = row.get("Quantidade de unidades por caixa", None)

    # cria o ItemMarketplace a partir dos valores crus
    if raw_box_type is not None:
        print(f"[INFO] Valor bruto de Tipo Caixa: {raw_box_type}")
        if raw_units_per_box is None or (math.isnan(raw_units_per_box)):
            raw_units_per_box=0
        item_marketplace = ItemMarketplace.from_row_values(raw_box_type, raw_units_per_box)
        item_marketplace.item = item.Code
        item.Product.ItemMarketplace = item_marketplace

        # For Package items (Garrafeira/Caixa vazada), set UnitsPerBox so PackageRule can place them.
        # Formula: min(csv_units or 1, amount) — places all available units in the fewest batches possible
        # without exceeding the box capacity from the catalog.
        if isinstance(item.Product, Package):
            csv_units = item_marketplace.units_per_box  # may be None if "Quantidade de unidades por caixa" is empty
            amount = int(getattr(item, 'Amount', 0) or 0)
            if amount > 0:
                units_per_box = int(min(csv_units or 1, amount))
            else:
                units_per_box = int(csv_units or 1)
            item.Product.UnitsPerBox = units_per_box

    return item

def enrich_items(items_list, combined_groups, support_point, df):
    """
    Enriquece os items com dados do DataFrame.
    Se houver múltiplas linhas para o código, prioriza unidades do estado de SP.
    """
    enriched = []

    for item in items_list:
        code = str(item.Code)

        if code not in df.index: 
            enriched.append(item)
            continue

        row_data = df.loc[code]

        # Caso múltiplas entradas
        if isinstance(row_data, pd.DataFrame):
            if len(row_data) > 1: 
                row_data = row_data[(row_data['Código Unb'] == 'None') | (row_data['Código Unb'] == 'nan')]
                row = row_data.iloc[0]
            elif len(row_data) == 1: 
                row = row_data.iloc[0]
            else: 
                row = row_data.iloc[0]

        else: 
            row = row_data

        enriched.append(fill_item_from_row(item, combined_groups, support_point, row))

    return enriched

def _log_items_count_by_type(items):
    """
    Conta e loga quantos items existem por tipo de produto.
    """
    # Inicializa contadores
    counts = {
        'chopp': 0,
        'returnable': 0,
        'isotonic_water': 0,
        'disposable': 0,
        'package': 0,
        'box_template': 0,
        'unknown': 0
    }
    
    # Total de unidades por tipo
    amounts = {
        'chopp': 0,
        'returnable': 0,
        'isotonic_water': 0,
        'disposable': 0,
        'package': 0,
        'box_template': 0,
        'unknown': 0
    }
    
    # Percorre todos os items
    for item in items:
        product = item.Product
        amount = getattr(item, 'Amount', 0) or 0
        
        if not product:
            counts['unknown'] += 1
            amounts['unknown'] += amount
            continue
        
        # Identifica tipo do produto
        product_type = type(product).__name__
        
        if product_type == 'Chopp' or isinstance(product, Chopp):
            counts['chopp'] += 1
            amounts['chopp'] += amount
        elif product_type == 'Returnable' or isinstance(product, Returnable):
            counts['returnable'] += 1
            amounts['returnable'] += amount
        elif product_type == 'IsotonicWater' or isinstance(product, IsotonicWater):
            counts['isotonic_water'] += 1
            amounts['isotonic_water'] += amount
        elif product_type == 'DisposableProduct' or isinstance(product, DisposableProduct):
            counts['disposable'] += 1
            amounts['disposable'] += amount
        elif product_type == 'Package' or isinstance(product, Package):
            counts['package'] += 1
            amounts['package'] += amount
        elif product_type == 'BoxTemplate' or isinstance(product, BoxTemplate):
            counts['box_template'] += 1
            amounts['box_template'] += amount
        else:
            counts['unknown'] += 1
            amounts['unknown'] += amount
    
    # Log resumo
    total_items = len(items)
    total_units = sum(amounts.values())
    
    # print("\n" + "="*80)
    # print("📊 RESUMO DOS ITEMS ENRIQUECIDOS")
    # print("="*80)
    # print(f"Total de Items: {total_items}")
    # print(f"Total de Unidades: {total_units}")
    # print("-"*80)
    
    if counts['chopp'] > 0:
        print(f"🍺 Chopp (Barril):        {counts['chopp']:4d} items | {amounts['chopp']:6d} unidades")
    
    if counts['returnable'] > 0:
        print(f"♻️  Returnable:            {counts['returnable']:4d} items | {amounts['returnable']:6d} unidades")
    
    if counts['isotonic_water'] > 0:
        print(f"💧 Isotonic Water:        {counts['isotonic_water']:4d} items | {amounts['isotonic_water']:6d} unidades")
    
    if counts['disposable'] > 0:
        print(f"🥤 Disposable:            {counts['disposable']:4d} items | {amounts['disposable']:6d} unidades")
    
    if counts['package'] > 0:
        print(f"📦 Package:               {counts['package']:4d} items | {amounts['package']:6d} unidades")
    
    if counts['box_template'] > 0:
        print(f"📋 Box Template:          {counts['box_template']:4d} items | {amounts['box_template']:6d} unidades")
    
    if counts['unknown'] > 0:
        print(f"❓ Unknown/No Product:    {counts['unknown']:4d} items | {amounts['unknown']:6d} unidades")
    
    print("="*80 + "\n")
