import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents, health, requests, reviews, runtime

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="BuildGate API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(runtime.router)
app.include_router(requests.router)
app.include_router(documents.router)
app.include_router(reviews.router)
