#!/usr/bin/env bash
# Corre cada escenario en un cluster nuevo y guarda la salida de check.py en
# salidas/<escenario>.txt. Uso: bash correr_escenarios.sh [--docker]
set -u
cd "$(dirname "$0")"
MODO="--local"; [ "${1:-}" = "--docker" ] && MODO=""
mkdir -p salidas
for esc in normal replica lider particion falla; do
  echo "=== $esc"
  python3 cluster.py up $MODO
  python3 scenarios/$esc.py > salidas/$esc.escenario.txt 2>&1
  python3 cluster.py down
  dir=$(ls -td historiales/*/ | head -1)
  python3 check.py "$dir$esc.jsonl" --run "$dir" > salidas/$esc.txt
  echo "check.py: $(tail -1 salidas/$esc.txt)  (historial en $dir)"
done
