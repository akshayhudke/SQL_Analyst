# QuerySense on OpenShift (Step-by-Step)

This guide shows how to deploy QuerySense on OpenShift with PostgreSQL, Ollama, the backend API, and the frontend UI.

> MVP note: the frontend container runs Vite dev server. For production, switch to a static build + NGINX.

## 0) Prerequisites
- An OpenShift cluster and the `oc` CLI installed.
- A project/namespace where you can create resources.
- Permission to build or push images.

## 1) Create a Project
```bash
oc login https://<cluster-api>
oc new-project querysense
```

## 2) Build Images (Choose One)

### Option A — Build inside OpenShift (Dockerfile strategy)
OpenShift can build images from Dockerfiles in a Git repo.

```bash
# Backend
oc new-app https://github.com/<you>/SQL_Analyst.git \
  --context-dir=backend \
  --strategy=docker \
  --name=qs-backend

# Frontend
oc new-app https://github.com/<you>/SQL_Analyst.git \
  --context-dir=frontend \
  --strategy=docker \
  --name=qs-frontend
```

### Option B — Build locally and push to the internal registry
If you prefer local builds, push images to the internal registry.

```bash
oc login https://<cluster-api>
oc project querysense

# Grant registry push permissions
oc policy add-role-to-user registry-editor $(oc whoami)

# Login to the registry (route may need to be enabled by your cluster admin)
REGISTRY=$(oc get route -n openshift-image-registry -o jsonpath='{.items[0].spec.host}')
podman login -u $(oc whoami) -p $(oc whoami -t) $REGISTRY

# Build and push backend
podman build -t $REGISTRY/querysense/backend:latest ./backend
podman push $REGISTRY/querysense/backend:latest

# Build and push frontend
podman build -t $REGISTRY/querysense/frontend:latest ./frontend
podman push $REGISTRY/querysense/frontend:latest
```

## 3) Create Secrets and ConfigMaps
```bash
oc create secret generic qs-db \
  --from-literal=POSTGRES_USER=sqluser \
  --from-literal=POSTGRES_PASSWORD=sqlpass \
  --from-literal=POSTGRES_DB=sqllab

oc create configmap qs-init-sql --from-file=init.sql=./db/init.sql
```

## 4) Create Persistent Volumes (PVCs)
Save as `pvc.yaml` and apply:
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: qs-postgres-pvc
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 20Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: qs-ollama-pvc
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 50Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: qs-backend-pvc
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 5Gi
```

```bash
oc apply -f pvc.yaml
```

## 5) Deploy PostgreSQL
Save as `postgres.yaml`:
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: qs-postgres
spec:
  serviceName: qs-postgres
  replicas: 1
  selector:
    matchLabels:
      app: qs-postgres
  template:
    metadata:
      labels:
        app: qs-postgres
    spec:
      securityContext:
        fsGroup: 1001
      containers:
      - name: postgres
        image: postgres:16
        envFrom:
        - secretRef:
            name: qs-db
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
        - name: init
          mountPath: /docker-entrypoint-initdb.d/init.sql
          subPath: init.sql
      volumes:
      - name: init
        configMap:
          name: qs-init-sql
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 20Gi
---
apiVersion: v1
kind: Service
metadata:
  name: qs-postgres
spec:
  selector:
    app: qs-postgres
  ports:
  - port: 5432
    targetPort: 5432
```

```bash
oc apply -f postgres.yaml
```

## 6) Deploy Ollama
Use `OLLAMA_MODELS` so models live on the PVC. Save as `ollama.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: qs-ollama
spec:
  replicas: 1
  selector:
    matchLabels:
      app: qs-ollama
  template:
    metadata:
      labels:
        app: qs-ollama
    spec:
      securityContext:
        fsGroup: 1001
      containers:
      - name: ollama
        image: ollama/ollama:latest
        env:
        - name: OLLAMA_MODELS
          value: /models
        ports:
        - containerPort: 11434
        volumeMounts:
        - name: ollama
          mountPath: /models
      volumes:
      - name: ollama
        persistentVolumeClaim:
          claimName: qs-ollama-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: qs-ollama
spec:
  selector:
    app: qs-ollama
  ports:
  - port: 11434
    targetPort: 11434
```

```bash
oc apply -f ollama.yaml
```

> If Ollama cannot write to the model directory because of OpenShift’s restricted SCC, you may need to add the service account to the `anyuid` SCC (cluster-admin action).

## 7) Deploy Backend
Save as `backend.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: qs-backend
spec:
  replicas: 1
  selector:
    matchLabels:
      app: qs-backend
  template:
    metadata:
      labels:
        app: qs-backend
    spec:
      containers:
      - name: backend
        image: <REGISTRY>/querysense/backend:latest
        env:
        - name: DATABASE_URL
          value: postgresql://sqluser:sqlpass@qs-postgres:5432/sqllab
        - name: OLLAMA_URL
          value: http://qs-ollama:11434
        - name: OLLAMA_MODEL
          value: qwen2.5:7b
        - name: LLM_ONLY_REWRITE
          value: "true"
        - name: TRAINING_STORE_ENABLED
          value: "true"
        ports:
        - containerPort: 8000
        volumeMounts:
        - name: backend-data
          mountPath: /app/data
      volumes:
      - name: backend-data
        persistentVolumeClaim:
          claimName: qs-backend-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: qs-backend
spec:
  selector:
    app: qs-backend
  ports:
  - port: 8000
    targetPort: 8000
```

```bash
oc apply -f backend.yaml
```

## 8) Deploy Frontend
Save as `frontend.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: qs-frontend
spec:
  replicas: 1
  selector:
    matchLabels:
      app: qs-frontend
  template:
    metadata:
      labels:
        app: qs-frontend
    spec:
      containers:
      - name: frontend
        image: <REGISTRY>/querysense/frontend:latest
        env:
        - name: VITE_API_URL
          value: http://qs-backend:8000
        ports:
        - containerPort: 5173
---
apiVersion: v1
kind: Service
metadata:
  name: qs-frontend
spec:
  selector:
    app: qs-frontend
  ports:
  - port: 5173
    targetPort: 5173
```

```bash
oc apply -f frontend.yaml
```

## 9) Expose Routes
```bash
oc expose service qs-backend
oc expose service qs-frontend
oc get routes
```

If the UI is accessed outside the cluster, update `VITE_API_URL` to the backend route hostname.

## 10) Pull the LLM Model in the Cluster
```bash
oc exec deploy/qs-ollama -- ollama pull qwen2.5:7b
```

## 11) Verify
```bash
oc logs deploy/qs-backend
oc logs deploy/qs-ollama
oc get pods
```

Open the frontend route in your browser and run a query to confirm analysis is working.

## Notes
- The sample data load (1M orders) can take minutes on first boot.
- `EXPLAIN ANALYZE` executes the query. Use with care in shared clusters.
