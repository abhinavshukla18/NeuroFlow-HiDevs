# Deploying NeuroFlow to Railway

Services: **postgres** (pgvector), **Redis**, **mlflow**, **api** (API + background worker in one
container), **frontend**. The worker runs inside the api container because Railway services cannot
share a disk, and the worker reads uploaded files that the API saved to `/data/uploads`.

Deploy from the branch that contains everything (`task-17`, or `main` after merging). Layers are
deployed in order and checked before adding the next.

## 0. Prerequisites
- Railway account (railway.com, sign in with GitHub) with the repo connected.
- Generate secrets locally (run 5 times, one per secret):
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`
  Needed: POSTGRES_PASSWORD, JWT_SECRET, ADMIN_CLIENT_SECRET, QUERY_CLIENT_SECRET.

## 1. Postgres (pgvector)
1. New Project, then Empty Project, named `neuroflow`.
2. New, GitHub Repo, select this repo. Rename the service to `postgres`.
3. Settings: Branch `task-17`, Dockerfile path `infra/postgres/Dockerfile`.
4. Variables: `POSTGRES_DB=neuroflow`, `POSTGRES_USER=neuroflow`, `POSTGRES_PASSWORD=<secret>`,
   `PGDATA=/var/lib/postgresql/data/pgdata`.
5. Add a Volume mounted at `/var/lib/postgresql/data`. Deploy.
6. Verify: deployment logs show `database system is ready to accept connections` and the init
   scripts running.

## 2. Redis
New, Database, Redis. It exposes `REDISHOST`, `REDISPORT`, `REDISPASSWORD`.
Rename the service to `Redis`.

## 3. MLflow
1. New, GitHub Repo (same repo), rename `mlflow`.
2. Settings: Branch `task-17`, Root Directory `infra/mlflow`.
3. Start command:
   `sh -c 'mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$POSTGRES_HOST:5432/mlflow'`
4. Variables: `POSTGRES_USER=neuroflow`, `POSTGRES_PASSWORD=${{postgres.POSTGRES_PASSWORD}}`,
   `POSTGRES_HOST=${{postgres.RAILWAY_PRIVATE_DOMAIN}}`, `PORT=5000`,
   `MLFLOW_SERVER_ALLOWED_HOSTS=<private-domain>:5000,<private-domain>,<public-domain>`.
5. Networking: Generate Domain (port 5000). Add the generated domain to
   `MLFLOW_SERVER_ALLOWED_HOSTS` and redeploy.
6. Verify: the public domain opens the MLflow UI.

## 4. API (+ worker)
1. New, GitHub Repo, rename `api`.
2. Settings: Branch `task-17`, Dockerfile path `backend/Dockerfile`, Healthcheck path `/health`.
3. Start command: `sh -c "python -m worker & exec uvicorn main:app --host 0.0.0.0 --port 8000"`
4. Variables (see `.env.example`):
   `PORT=8000`, `POSTGRES_HOST=${{postgres.RAILWAY_PRIVATE_DOMAIN}}`,
   `POSTGRES_PASSWORD=${{postgres.POSTGRES_PASSWORD}}`, `REDIS_HOST=${{Redis.REDISHOST}}`,
   `REDIS_PORT=${{Redis.REDISPORT}}`, `REDIS_PASSWORD=${{Redis.REDISPASSWORD}}`,
   `MLFLOW_TRACKING_URI=http://${{mlflow.RAILWAY_PRIVATE_DOMAIN}}:5000`,
   `JWT_SECRET`, `ADMIN_CLIENT_ID`, `ADMIN_CLIENT_SECRET`, `QUERY_CLIENT_ID`, `QUERY_CLIENT_SECRET`,
   `OPENAI_API_KEY` (or `FAKE_EMBEDDINGS=true` without a key).
5. Networking: Generate Domain (port 8000). Verify: `GET <api-domain>/health`.

## 5. Frontend
1. New, GitHub Repo, rename `frontend`. Settings: Branch `task-17`, Root Directory `frontend`.
2. Variables: `NEXT_PUBLIC_API_URL=https://<api-domain>`, `PORT=3000`. Generate Domain.
3. On the **api** service set `CORS_ORIGINS=https://<frontend-domain>` and redeploy.

## 6. Production verification
Replace `API` with the api domain. Get a token first:

```powershell
$API="https://<api-domain>"
$t=(Invoke-RestMethod -Method Post "$API/auth/token" -ContentType application/json -Body (@{client_id="admin-client";client_secret="<ADMIN_CLIENT_SECRET>"}|ConvertTo-Json)).access_token
```

| # | Check | Command | Result |
|---|---|---|---|
| 1 | Health all green | `Invoke-RestMethod $API/health` | TODO |
| 2 | Ingest test PDF reaches `complete` | `curl.exe -X POST $API/ingest -H "Authorization: Bearer $t" -F "file=@tests/fixtures/test_doc.pdf;type=application/pdf"` then `GET /documents/{id}` | TODO |
| 3 | Cited answer | `POST /query` with `{"query":"What is the main topic of the document?","stream":false}` | TODO |
| 4 | Evaluation exists | `GET /evaluations` | TODO |
| 5 | Streaming | `curl.exe -N "$API/query/<run_id>/stream?token=$t"` (create run with `"stream":true`) | TODO |
| 6 | MLflow UI | open the mlflow public domain | TODO |
| 7 | Metrics | `Invoke-WebRequest $API/metrics` | TODO |
| 8 | Load test | see below | TODO |

Load test (set `DISABLE_RATE_LIMIT=1` on the api service first, remove it afterwards):

```powershell
locust -f tests/performance/locustfile.py -H $API --headless -u 10 -r 2 --run-time 2m
```

Results are written to `tests/performance/load_test_results.json`.

## 7. Rollback
1. **Redeploy a previous build:** service, Deployments, pick the last good deployment, Redeploy.
   Or point the service at an earlier image from GitHub Container Registry:
   `ghcr.io/<owner>/<repo>/api:<previous-commit-sha>`.
2. **Database:** the schema comes from `infra/init/*.sql`, which only runs on an empty volume. There
   are no automatic migrations. To undo a schema change, run a hand-written reverse SQL file
   (`railway connect postgres`, then `\i down.sql`).
3. **Verify:** `GET /health` is green, repeat checks 3 and 4 above, and confirm the deployment shows
   the expected commit SHA in the Railway dashboard.

## Live URLs
- API: TODO
- Frontend: TODO
- MLflow: TODO