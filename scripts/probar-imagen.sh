#!/usr/bin/env bash
# Prueba una imagen con las mismas restricciones que tendrá en el clúster: raíz de solo
# lectura, /tmp en memoria, sin capabilities y con el límite de memoria de su manifiesto.
# La usa el workflow Imagenes antes de publicar; también sirve en el Mac:
#   docker build -f docker/api.Dockerfile -t prueba:api . && scripts/probar-imagen.sh api prueba:api
# Uso: scripts/probar-imagen.sh <api|dashboard|pipeline|mlflow> <imagen>
set -euo pipefail

NOMBRE="${1:?uso: probar-imagen.sh <api|dashboard|pipeline|mlflow> <imagen>}"
IMAGEN="${2:?falta la imagen, por ejemplo check:api}"
CONTENEDOR="prueba-lima-rent-$NOMBRE"

# El mismo límite de memoria que el manifiesto de cada carga (deploy/k3s/base).
case "$NOMBRE" in
  api) MEM=512m ;;
  dashboard | mlflow) MEM=768m ;;
  pipeline) MEM=2g ;;
  *) echo "Imagen desconocida: $NOMBRE" >&2; exit 2 ;;
esac
# Las mismas restricciones que el securityContext de los manifiestos.
LIMITES=(--read-only --tmpfs /tmp:rw,nosuid,size=512m --cap-drop ALL
  --security-opt no-new-privileges --memory "$MEM" --memory-swap "$MEM")

limpiar() { docker rm -f "$CONTENEDOR" > /dev/null 2>&1 || true; }
trap limpiar EXIT
limpiar

espera() {
  for _ in $(seq 1 40); do curl -fsS "$1" > /dev/null 2>&1 && return 0; sleep 1; done
  echo "::error::$NOMBRE no respondió en $1"
  docker logs --tail 30 "$CONTENEDOR" || true
  return 1
}
# Tras responder, el servidor debe seguir vivo: un proceso que supera el límite de memoria
# puede contestar una vez y morir segundos después (OOM).
sigue_vivo() {
  sleep 10
  estado=$(docker inspect -f '{{.State.Running}}/{{.State.OOMKilled}}' "$CONTENEDOR")
  if [ "$estado" != "true/false" ]; then
    echo "::error::$NOMBRE murió tras arrancar (running/oom = $estado)"
    docker logs --tail 30 "$CONTENEDOR" || true
    return 1
  fi
  docker stats --no-stream --format "$NOMBRE: memoria {{.MemUsage}}" "$CONTENEDOR"
}

case "$NOMBRE" in
  pipeline)
    # Una semana sintética completa dentro de la imagen: limpia, entrena y promueve.
    docker run --rm --name "$CONTENEDOR" "${LIMITES[@]}" -e DATA_URI=/tmp/data \
      -e MLFLOW_TRACKING_URI=sqlite:////tmp/mlflow.db -e OPTUNA_TRIALS=2 \
      "$IMAGEN" sh -c 'lima-rent weekly --fixture 300 &&
        test -s /tmp/data/models/champion/meta.json'
    ;;
  api)
    docker run -d --name "$CONTENEDOR" "${LIMITES[@]}" -p 127.0.0.1:8080:8080 "$IMAGEN" > /dev/null
    espera http://127.0.0.1:8080/api/health
    # Sin champion en el lago, la API está viva pero no lista.
    test "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/ready)" = 503
    sigue_vivo
    ;;
  dashboard)
    docker run -d --name "$CONTENEDOR" "${LIMITES[@]}" -p 127.0.0.1:8501:8501 "$IMAGEN" > /dev/null
    espera http://127.0.0.1:8501/_stcore/health
    sigue_vivo
    ;;
  mlflow)
    docker run -d --name "$CONTENEDOR" "${LIMITES[@]}" -p 127.0.0.1:5000:5000 \
      -e MLFLOW_BACKEND_STORE_URI=sqlite:////tmp/mlflow.db \
      -e MLFLOW_ARTIFACTS_DESTINATION=/tmp/artifacts \
      -e MLFLOW_ALLOWED_HOSTS=127.0.0.1,127.0.0.1:5000 "$IMAGEN" > /dev/null
    espera http://127.0.0.1:5000/health
    sigue_vivo
    ;;
esac
echo "$NOMBRE: OK"
