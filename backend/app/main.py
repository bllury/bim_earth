import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.ifc import create_ifc_router
from .services.ifc_converter import ConverterService
from .services.ifcopenshell_converter import IfcOpenShellConverter
from .services.mock_converter import MockConverter
from .services.persistence import PersistenceStore


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("IFC_DATA_DIR", str(BACKEND_ROOT / "data")))
TEMP_DIR = DATA_DIR / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
store = PersistenceStore(DATA_DIR)

CONVERTER_MODE = os.getenv("IFC_CONVERTER_MODE", "ifcopenshell").strip().lower()

if CONVERTER_MODE == "mock":
    converter = MockConverter()
else:
    converter = IfcOpenShellConverter()

service = ConverterService(
    converter=converter,
    output_root=TEMP_DIR,
    persistence=store,
)

app = FastAPI(title="BIM IFC Converter")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(create_ifc_router(service, store))
