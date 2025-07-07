import uvicorn
import os
import sys
from fastapi import FastAPI, Response, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sane
from PIL import Image
import pytesseract
import shutil
import uuid
from pydantic import BaseModel
from io import BytesIO
from PyPDF2 import PdfMerger
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Map of uuid to PIL images
scan_memory = {}


class ScanRequest(BaseModel):
    scan_id: str = None
    device_name: str
    mode: str = "color"
    resolution: int = 300


@app.get("/index.html")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/scanners")
def get_scanners():
    devices = sane.get_devices()

    if not devices:
        return []

    scanners = []
    for device in devices:
        name, vendor, model, dev_type = device
        scanners.append(
            {"name": name, "vendor": vendor, "model": model, "dev_type": dev_type}
        )
    return scanners


@app.post("/scan")
def trigger_scan(scan_request: ScanRequest):
    scan_id = scan_request.scan_id
    if scan_id is None:
        scan_id = str(uuid.uuid4())

    scanner = sane.open(scan_request.device_name)
    scanner.mode = scan_request.mode
    scanner.resolution = scan_request.resolution

    scan_dev = scanner.scan()
    img = scan_dev
    scanner.close()

    if scan_id not in scan_memory:
        scan_memory[scan_id] = [img]
    else:
        scan_memory[scan_id].append(img)

    return {"scan_id": scan_id, "page_count": len(scan_memory.get(scan_id, []))}


@app.get("/scan/{scan_id}/info")
def scan_info(scan_id: str):
    return {"scan_id": scan_id, "page_count": len(scan_memory.get(scan_id, []))}


@app.get("/scan/{scan_id}/image/{index}")
def scan_get_image(scan_id: str, index: int):
    if scan_id not in scan_memory:
        raise HTTPException(status_code=404, detail="Scan ID not found")

    if index < 0 or index >= len(scan_memory[scan_id]):
        raise HTTPException(status_code=404, detail="Image index out of range")

    image = scan_memory[scan_id][index]

    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    buffer.seek(0)

    return Response(content=buffer.read(), media_type="image/jpeg")


@app.get("/finish_scan/{scan_id}")
def finish_scan(scan_id: str):
    if scan_id not in scan_memory:
        raise HTTPException(status_code=404, detail="Scan ID not found")

    images = scan_memory[scan_id]
    output_dir = os.getenv("SCANLESS_OUTPUT_DIR", "/tmp")
    os.makedirs(output_dir, exist_ok=True)
    pdf_filename = f"scan_{scan_id}_ocr.pdf"
    pdf_filepath = os.path.join(output_dir, pdf_filename)

    try:
        merger = PdfMerger()
        for img in images:
            pdf_bytes = pytesseract.image_to_pdf_or_hocr(img, extension="pdf")
            merger.append(BytesIO(pdf_bytes))
        with open(pdf_filepath, "wb") as file_out:
            merger.write(file_out)
        merger.close()

        # Also stream back to client
        output_buffer = BytesIO()
        with open(pdf_filepath, "rb") as file_in:
            output_buffer.write(file_in.read())
        output_buffer.seek(0)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create searchable PDF: {e}"
        )

    return Response(
        content=output_buffer.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pdf_filename}"'},
    )


if __name__ == "__main__":
    sane.init()

    port = int(os.getenv("SCANLESS_PORT", "7500"))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
    )
