#!/usr/bin/env bash
# Guarda datos/ en el repo aunque otra corrida haya guardado en el medio (lo usan los workflows).
#   bash guardar.sh "mensaje" [rehacer]
# Los archivos de cada día no chocan entre corridas; si chocan, gana lo de esta corrida (es lo más nuevo).
# Con "rehacer", el índice y los CSV generales se vuelven a armar con todos los días después de juntar.
set -e
git config user.name "flujo-bot"
git config user.email "flujo-bot@users.noreply.github.com"
git add datos
git diff --cached --quiet && exit 0
git commit -q -m "$1"
for intento in 1 2 3 4 5; do
  git fetch -q origin main
  git rebase -q -X theirs origin/main
  if [ "$2" = "rehacer" ]; then
    python -c "import flujo; flujo.publicar()"
    git add datos
    git diff --cached --quiet || git commit -q --amend --no-edit
  fi
  git push -q origin HEAD:main && exit 0
  sleep $((intento * 10))
done
exit 1
