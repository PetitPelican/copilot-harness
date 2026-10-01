#!/bin/sh
# Construit le programme des Rappels, sur un Mac — nulle part ailleurs il n'a
# de sens. Le résultat se pose à côté du programme du harnais, qui le trouve là.
#
#     rappels/construire.sh [dossier-de-sortie]     (défaut : rappels/)
set -eu
ICI=$(cd "$(dirname "$0")" && pwd)
SORTIE="${1:-$ICI}"
# `-swift-version 5` : le mode strict de Swift 6 refuse la capture d'un
# résultat dans le rappel asynchrone du magasin ; la boîte le rend sûr, le
# mode 5 évite de le prouver au compilateur à chaque ligne.
swiftc -O -swift-version 5 "$ICI/Rappels.swift" -o "$SORTIE/rappels-darwin-arm64"
"$SORTIE/rappels-darwin-arm64" acces >/dev/null 2>&1 || true
echo "$SORTIE/rappels-darwin-arm64"
