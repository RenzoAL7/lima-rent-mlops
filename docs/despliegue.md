# Despliegue en producción

AlquiLima corre en el clúster [K3s-Cortex](https://github.com/RenzoAL7/K3s-Cortex): una VM Ampere A1 de OCI (arm64, 3 OCPU / 20 GB, Always Free) compartida con otros proyectos. Lo gestiona Argo CD con el mismo flujo GitOps que peru-spend-tracker.

## Flujo

1. Un push a `main` ejecuta CI (`ci.yml`): ruff, pytest, dos semanas simuladas y render de los manifiestos.
2. `images.yml` construye las cuatro imágenes (`api`, `dashboard`, `pipeline` y `mlflow`) **solo para arm64**, en runners ARM nativos (`ubuntu-24.04-arm`), sin QEMU. Antes de publicar, prueba cada una con las restricciones del clúster: raíz de solo lectura, `/tmp` en tmpfs y sin capabilities. La imagen del pipeline corre una semana sintética completa.
3. Las imágenes se publican en GHCR con el tag `sha-<commit>` y se guarda el digest de cada una.
4. El job `promote` ejecuta `scripts/promote.py`, que copia `deploy/k3s` a `apps/lima-rent-mlops` en K3s-Cortex y fija los cuatro digests en el overlay `prod`. Después hace un commit directo en `main` de Cortex.
5. El webhook de GitHub avisa a Argo CD, que sincroniza en segundos. Para revertir, se revierte ese commit en K3s-Cortex.

Un **modelo nuevo no necesita despliegue**. El CronJob lo exporta a `models/champion/` en el bucket y la API lo recarga en menos de 5 minutos (`MODEL_RELOAD_SECONDS`).

## Qué corre en el namespace `lima-rent`

| Recurso | Réplicas | Memoria (request / límite) | Expuesto |
|---|---|---|---|
| `lima-rent-api` (FastAPI) | 2 | 160 Mi / 512 Mi | `/api` en el Ingress |
| `lima-rent-dashboard` (Streamlit) | 1 | 256 Mi / 768 Mi | `/` en el Ingress |
| `lima-rent-mlflow` | 1 | 320 Mi / 768 Mi | No (port-forward) |
| `lima-rent-postgres` (StatefulSet, 1 Gi) | 1 | 96 Mi / 256 Mi | No |
| CronJob `lima-rent-weekly` (lunes 06:00, Lima) | — | 640 Mi / 2 Gi | — |
| CronJob `lima-rent-context` (día 2 de cada mes) | — | 512 Mi / 1.5 Gi | — |

En reposo pide alrededor de 1 GB. La `ResourceQuota` del namespace limita la suma de límites a 7 Gi, para que una corrida del pipeline no afecte a los demás proyectos del clúster.

Las `NetworkPolicy` permiten solo estos caminos:

- Postgres solo acepta conexiones de MLflow.
- MLflow solo acepta conexiones del pipeline.
- La API recibe tráfico del dashboard y de Traefik.
- El dashboard recibe tráfico solo de Traefik.

Todos los pods corren como usuario 1000, con raíz de solo lectura y sin token de la API de Kubernetes.

## Pasos únicos (a mano)

### 1. Claves de Object Storage

El bucket `lima-rent-mlops` ya existe (us-ashburn-1, privado). En la consola de OCI, ve a **Perfil → Customer secret keys → Generate secret key**. El secreto se muestra una sola vez.

### 2. Secrets en el clúster

```bash
scripts/crear-secretos.sh OCI_VM
```

Pide las claves por teclado y las envía por SSH sin dejarlas en el historial. Crea dos Secrets: `lima-rent-s3` (endpoint y claves) y `lima-rent-postgres` (contraseña aleatoria). Así cada pod recibe solo lo que usa. Si lo vuelves a correr, actualiza las claves S3 y conserva la contraseña de Postgres.

### 3. Token para promover

El job `promote` necesita el secreto `CORTEX_REPO_TOKEN` en este repositorio: un token con permiso de escritura de contenido sobre `RenzoAL7/K3s-Cortex`. Es el mismo que usa peru-spend-tracker.

```bash
gh secret set CORTEX_REPO_TOKEN --repo RenzoAL7/lima-rent-mlops
```

### 4. Registrar la aplicación en Argo CD

En K3s-Cortex:

```bash
cp ../lima-rent-mlops/deploy/argocd/lima-rent-application.yaml clusters/rnz-prod/
# Agregar "  - lima-rent-application.yaml" a clusters/rnz-prod/kustomization.yaml
git add clusters/rnz-prod && git commit -m "feat(lima-rent): registrar la aplicación" && git push
```

`promote.py` se niega a escribir en Cortex si esa Application no existe o apunta a otro lado. Hasta la primera promoción, Argo CD la muestra con error porque `apps/lima-rent-mlops` aún no existe. Es normal.

### 5. Primera publicación de imágenes

Haz push a `main` (o ejecuta **Imagenes** a mano desde Actions). Cuando termine, en GitHub → Packages, cambia la visibilidad de los cuatro paquetes `lima-rent-*` a **Public**, igual que los de peru-spend-tracker. Si siguen privados, los pods quedan en `ImagePullBackOff`.

### 6. Dominio

En Cloudflare, crea un registro `A` llamado `lima-rent` que apunte a la IP del balanceador de OCI, con el proxy activado. Usa el mismo modo SSL **Flexible** que el resto de `renzoaguilar.dev`: el balanceador solo reenvía el puerto 80 a Traefik. El Ingress responde solo al host `lima-rent.renzoaguilar.dev`, así que no interfiere con las rutas de los otros proyectos.

### 7. Primera corrida

No hace falta esperar al lunes:

```bash
kubectl -n lima-rent create job --from=cronjob/lima-rent-context lima-rent-contexto-inicial
kubectl -n lima-rent create job --from=cronjob/lima-rent-weekly lima-rent-primera
kubectl -n lima-rent logs -f job/lima-rent-primera
```

La primera corrida hace scraping (unos 20 minutos a 4 s por página), entrena el modelo inicial y lo promueve. Después:

```bash
curl https://lima-rent.renzoaguilar.dev/api/ready
curl https://lima-rent.renzoaguilar.dev/api/status
```

## Operación

- **MLflow** no se expone a internet:

  ```bash
  kubectl -n lima-rent port-forward svc/lima-rent-mlflow 5000:5000
  ```

  Luego abre http://localhost:5000.

- **Forzar un reentrenamiento:** crea un Job desde el CronJob y agrégale la variable `FORCE_RETRAIN` con la razón, que queda registrada en MLflow y en el historial:

  ```bash
  kubectl -n lima-rent create job --from=cronjob/lima-rent-weekly lima-rent-retrain --dry-run=client -o yaml \
    | kubectl set env --local -f - FORCE_RETRAIN="reentrenamiento manual" -o yaml \
    | kubectl apply -f -
  ```

- **Alertas:** `monitor.yml` revisa cada 3 horas el dashboard, `/api/ready`, una predicción de prueba y que la última corrida haya terminado bien y tenga como máximo 8 días. Si algo falla, abre o actualiza un issue (GitHub lo notifica por correo) y lo cierra cuando todo vuelve a responder.
- **Revertir un modelo:** en MLflow, mueve el alias `champion` a la versión anterior y copia sus archivos a `models/champion/`. El historial de decisiones está en `models/history.json` y en la página *Historial de modelos*.
