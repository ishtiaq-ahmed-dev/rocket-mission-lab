"""Single-process production preview: built assets and /api on loopback."""
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from .api import app as api
from .config import ROOT


def create_preview(directory=None):
    preview=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    preview.add_middleware(GZipMiddleware,minimum_size=2048,compresslevel=3)
    preview.mount('/api',api)
    preview.mount('/',StaticFiles(directory=directory or ROOT/'frontend/dist',html=True,check_dir=False))
    return preview


app=create_preview()
