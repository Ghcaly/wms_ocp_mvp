from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
import xml.etree.ElementTree as ET
from ...service.palletizing_processor import PalletizingProcessor
from ...adapters.logger_instance import set_logger, clear_logger
from ...adapters.logger_system import JsonStepLogger

from pathlib import Path
import uuid

router = APIRouter(prefix="/xml", tags=["XML"])

async def request_logger_dependency():
    data_dir = Path(__file__).parent.parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    filename = f"process_log_{uuid.uuid4().hex[:8]}.json"
    logger_inst = JsonStepLogger(filepath=str(data_dir / filename))
    set_logger(logger_inst)
    try:
        yield logger_inst
    finally:
        try:
            logger_inst.save()  # salva no filepath já configurado
        except Exception:
            pass
        
@router.post("/process")
async def process_xml(file: UploadFile = File(...), _logger=Depends(request_logger_dependency)):
    if file.content_type not in ("application/xml", "text/xml"):
        raise HTTPException(status_code=400, detail="Arquivo inválido")

    content = await file.read()

    try:
        ET.fromstring(content)
    except ET.ParseError:
        raise HTTPException(
            status_code=400,
            detail="Conteúdo não é um XML válido"
        )

    # run palletization using an instance (synchronous)
    try:
        processor = PalletizingProcessor(debug_enabled=True)
        result = processor.run_from_xml(content, filename=file.filename)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar o XML: {str(e)}"
        )

    if result and result.get('success') is False:
        raise HTTPException(status_code=500, detail=result.get('error', 'Erro desconhecido'))

    # Build response from JSON output file
    import json as _json
    from pathlib import Path as _Path
    data_dir = _Path(__file__).parent.parent.parent / "data"
    ctx = result.get('context') if result else None
    map_number = getattr(ctx, 'MapNumber', None) if ctx else None
    palletize_json = None
    if map_number:
        json_path = data_dir / f"palletize_result_map_{map_number}.json"
        if json_path.exists():
            with open(json_path, encoding='utf-8') as f:
                palletize_json = _json.load(f)

    return palletize_json or {
        "filename": file.filename,
        "bytes": len(content),
        "message": "Paletização concluída"
    }
