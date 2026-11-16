#!/usr/bin/env bash
# Pose les données figées de la PR dans le dossier de travail du cas (lancé par `--scaffold`).
set -eu
cp -R "$(dirname "$0")/fixtures" ./fixtures
