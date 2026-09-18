#!/usr/bin/env bash
# ¿Se movió la rama base (feature/PQRSdev) desde que salimos?
#
# Si avanzó, hay que traer sus cambios a feature/trx-esqueleto ANTES de que
# Fabián revise el PR: los conflictos se resuelven mejor aquí, con contexto,
# que en el merge del PR.
#
# MERGE, no rebase: nuestra rama ya está publicada y el rebase reescribiría los
# commits, obligando a push --force sobre una rama que otros pueden tener
# descargada.

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git fetch origin feature/PQRSdev feature/trx-esqueleto -q 2>/dev/null || true

BASE=$(git merge-base HEAD origin/feature/PQRSdev)
SUYOS=$(git rev-list --count "$BASE"..origin/feature/PQRSdev)
MIOS=$(git rev-list --count "$BASE"..HEAD)
SIN_SUBIR=$(git rev-list --count origin/feature/trx-esqueleto..HEAD 2>/dev/null || echo "?")

echo "  rama actual : $(git branch --show-current)"
echo "  sin subir   : $SIN_SUBIR commit(s)"
echo "  nuestros    : $MIOS commit(s) sobre la base"
echo "  de PQRSdev  : $SUYOS commit(s) nuevos desde que salimos"

if [ "$SUYOS" -eq 0 ]; then
  echo "  => al día: nada que traer"
  exit 0
fi

echo
echo "  PQRSdev AVANZÓ. Lo que trae:"
git log --oneline "$BASE"..origin/feature/PQRSdev | sed 's/^/    /'
echo
echo "  ficheros tocados por AMBOS (posible conflicto):"
comm -12 <(git diff --name-only "$BASE" HEAD | sort) \
         <(git diff --name-only "$BASE" origin/feature/PQRSdev | sort) | sed 's/^/    /' \
  || echo "    ninguno"
echo
echo "  para ponerse al día:"
echo "    git merge origin/feature/PQRSdev"
echo "    # resolver, correr los 3 verificadores y push"
