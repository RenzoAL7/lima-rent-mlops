#!/bin/sh
# Recorta del entorno virtual lo que una imagen nunca usa al ejecutarse. Corre en la etapa de
# construcción (ver docker/*.Dockerfile), así que lo borrado no llega a la imagen final.
# Uso: podar-venv.sh /opt/venv
set -eu

VENV="${1:?uso: podar-venv.sh <venv>}"
cd "$VENV"/lib/python3.*/site-packages
antes=$(du -sm . | cut -f1)

# 1. Suites de pruebas que las librerías publican dentro del paquete (pandas, numpy, scipy,
#    pyarrow, scikit-learn...). Son el mayor peso muerto: entre 65 y 120 MB por imagen.
find . -type d -name tests -prune -exec rm -rf {} +

# 2. Cabeceras y fuentes de C/Cython: solo sirven para compilar extensiones contra el paquete.
find . -type f \( -name '*.h' -o -name '*.hpp' -o -name '*.c' -o -name '*.cc' -o -name '*.cpp' \
  -o -name '*.pyx' -o -name '*.pxd' -o -name '*.pxi' -o -name '*.a' \) -delete
rm -rf pyarrow/include pyarrow/src

# 3. PyArrow trae clientes que aquí no se usan: Flight (RPC) y su propio cliente S3. El lago se
#    lee con boto3 (storage.py) y Parquet se procesa en memoria. libarrow_substrait se queda:
#    el núcleo de PyArrow enlaza contra ella y sin esa librería ni siquiera se importa.
rm -f pyarrow/libarrow_flight.so* pyarrow/libarrow_python_flight.so* pyarrow/_flight.*.so \
      pyarrow/libarrow_s3.so* pyarrow/_s3fs.*.so

# 4. botocore incluye la definición de cada servicio de AWS (~27 MB). Solo se habla S3 (el
#    bucket de OCI y los artefactos de MLflow). Si algún día hace falta otro servicio, agrégalo
#    a esta lista: el error sería "Unknown service" al crear el cliente.
if [ -d botocore/data ]; then
  find botocore/data -mindepth 1 -maxdepth 1 -type d ! -name s3 ! -name sts -exec rm -rf {} +
fi

# 5. Comprobación: si la poda rompió algo básico, la construcción falla aquí y no en el clúster.
"$VENV"/bin/python - <<'EOF'
import io

import boto3
import pandas as pd

buffer = io.BytesIO()
pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}).to_parquet(buffer, index=False)
assert pd.read_parquet(io.BytesIO(buffer.getvalue())).shape == (2, 2)
boto3.client("s3", region_name="us-ashburn-1", aws_access_key_id="x", aws_secret_access_key="x")
EOF

echo "podar-venv: $antes MB -> $(du -sm . | cut -f1) MB"
