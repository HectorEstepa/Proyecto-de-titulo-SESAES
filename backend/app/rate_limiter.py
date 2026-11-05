"""
Instancia única del rate limiter (slowapi), en su propio módulo para que
tanto main.py como cualquier router (ej. auth.py) puedan importarla sin
generar un import circular entre ellos.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
