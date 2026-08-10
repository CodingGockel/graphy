"""Reusable OpenAPI `responses` entries, composed per router via dict spread,
e.g. `responses={**RESP_502, **RESP_503, **RESP_500}`."""
from src.models.schemas import ErrorResponse

RESP_404 = {404: {"model": ErrorResponse, "description": "Resource not found."}}
RESP_500 = {500: {"model": ErrorResponse, "description": "Unexpected server error."}}
RESP_502 = {502: {"model": ErrorResponse, "description": "Upstream service returned an invalid response."}}
RESP_503 = {503: {"model": ErrorResponse, "description": "A dependent service is unavailable."}}
