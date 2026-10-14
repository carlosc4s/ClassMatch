"""
Entrada do ClassMatch na Vercel (função Python serverless).

A Vercel procura um objeto WSGI chamado "app" neste arquivo. Ele é o mesmo app Flask
do backend/app.py; no computador continua valendo o INICIAR.bat.
O frontend/ é entregue direto pela Vercel (veja o vercel.json).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

from app import app  # noqa: E402,F401
