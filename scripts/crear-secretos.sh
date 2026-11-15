#!/usr/bin/env bash
# Crea (o actualiza) los Secrets de lima-rent en el clúster K3s-Cortex:
#   lima-rent-s3        Customer Secret Key de OCI Object Storage (API compatible con S3).
#                       Se genera en la consola de OCI: Perfil > Customer secret keys.
#   lima-rent-postgres  Contraseña de la base de MLflow. Se genera una sola vez: si ya existe se
#                       conserva, porque Postgres guardó la anterior al inicializar su volumen.
# Las claves se piden por teclado y viajan por SSH en stdin: no quedan en el historial ni en Git.
# Uso: scripts/crear-secretos.sh [host-ssh]   (por defecto OCI_VM)
set -euo pipefail

HOST="${1:-OCI_VM}"
REGION="${OCI_REGION:-us-ashburn-1}"
NAMESPACE="${OCI_NAMESPACE:-$(oci os ns get --query data --raw-output 2>/dev/null || true)}"
if [ -z "$NAMESPACE" ]; then read -rp "Namespace de Object Storage: " NAMESPACE; fi

read -rp "Access key (columna Access key de la Customer secret key): " KEY
read -rsp "Secret key (se muestra una sola vez al generarla): " SECRET
echo

printf 'S3_ACCESS_KEY_ID=%s\nS3_SECRET_ACCESS_KEY=%s\nS3_ENDPOINT_URL=https://%s.compat.objectstorage.%s.oraclecloud.com\n' \
  "$KEY" "$SECRET" "$NAMESPACE" "$REGION" |
  ssh "$HOST" 'set -e; umask 077; f=$(mktemp); trap "rm -f $f" EXIT; cat > "$f"
    kubectl create namespace lima-rent --dry-run=client -o yaml | kubectl apply -f - > /dev/null
    kubectl -n lima-rent create secret generic lima-rent-s3 --from-env-file="$f" \
      --dry-run=client -o yaml | kubectl apply -f -
    if kubectl -n lima-rent get secret lima-rent-postgres > /dev/null 2>&1; then
      echo "lima-rent-postgres ya existía: se conserva su contraseña."
    else
      kubectl -n lima-rent create secret generic lima-rent-postgres \
        --from-literal=POSTGRES_PASSWORD="$(openssl rand -hex 24)"
    fi
    kubectl -n lima-rent get secrets'
