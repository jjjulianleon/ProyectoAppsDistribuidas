#!/usr/bin/env bash
# Levanta las 3 réplicas y el front en un solo paso. Uso: bash demo.sh [--docker]
# Abre http://localhost:8080/?parlante=1 (parlante) y http://localhost:8080/?u=ana (invitado).
# Para apagar: Ctrl+C y después python3 cluster.py down
set -e
cd "$(dirname "$0")"
MODO="--local"; [ "${1:-}" = "--docker" ] && MODO=""
python3 cluster.py up $MODO
exec python3 gateway.py
