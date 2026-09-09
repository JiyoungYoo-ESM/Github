# infra — esm-order-review (AWS CDK)

Account `634236767858`, region `ap-northeast-2`, existing VPC `vpc-0b52fdfc0139395d2`
(`sk-vibe-vpc-workload`, `10.204.0.0/22`).

Per environment (`esm-dev`, `esm-prd`) — **separate clusters**:

- ECS Fargate cluster + one service, **one task with two containers**: `frontend`
  (Next.js :3000, ALB target) → `backend` (FastAPI :8002) over localhost.
- Internet-facing ALB → frontend, health check `/login`.
- RDS PostgreSQL 16 (one instance per env, private).
- S3 bucket for durable analysis outputs.
- Secrets Manager: RDS credentials (auto) + `esm/<env>/app` (login hashes).

- ElastiCache Redis (`cache.t4g.micro`, single node, no TLS) — rate-limit/
  concurrency state + Celery broker. Scale up = bump `cacheNodeType` in
  `esm-stack.ts` (brief interruption).
- Celery worker service (same backend image, command override) on **Fargate
  Spot** — dev 1 task at 0.5 vCPU/1GB, prd 2 tasks at 1 vCPU/2GB each. Spot interruptions are safe:
  celery acks late, so unacked jobs redeliver after the broker visibility
  timeout (worst case ~2× task time limit before a job resumes).

Sentry is **not** provisioned (SENTRY_DSN empty → disabled).

## Infra deploys — local only (admin/SSO on the account)

CI has **no** cdk permissions. Every infrastructure change goes through a local
deploy by someone holding admin/SSO on account `634236767858`:

```bash
export AWS_PROFILE=stylekorean-mkt
aws sso login                       # when the session expired
cd infra && npm ci

# First time on a fresh account only:
#   npx cdk bootstrap aws://634236767858/ap-northeast-2
#   npx cdk deploy esm-cicd   # -c oidcProviderArn=... if the OIDC provider exists

npx cdk diff   esm-dev              # always review the diff first
npx cdk deploy esm-dev
npx cdk deploy esm-prd              # after dev is verified
```

See `RUNBOOK.md` for the ordered procedure and post-deploy checks.

## CI/CD

One workflow. CI ships application images; it never changes infrastructure.

- `.github/workflows/deploy.yml` (app) — push to `develop`/`main`. Separate
  `deploy-dev`/`deploy-prd` jobs: build images → push to per-env ECR repos as
  `:latest` (+ `:<sha>`) → `aws ecs update-service --force-new-deployment`.
  `concurrency: cancel-in-progress` so only the latest push deploys.

### Deploy role — least privilege

`sk-an2-role-esm-github-deploy` (created by `esm-cicd`) holds exactly what that
pipeline needs and nothing else:

| Allowed | Scope |
|---|---|
| `ecr:GetAuthorizationToken` | `*` (no resource scope exists for this action) |
| ECR pull/push | the four `sk-{dev,prd}-an2-ecr-esm-{backend,frontend}` repos |
| `ecs:UpdateService`, `ecs:DescribeServices` | the four esm app/worker services |

Deliberately **not** granted: `sts:AssumeRole` on `cdk-hnb659fds-*` and the
bootstrap `ssm:GetParameter`. Without those, `cdk deploy` from Actions fails with
AccessDenied — which is the point. Re-adding them hands anyone who can push to
`main` full control of the account.

The role also carries a permissions boundary, `sk-an2-pb-esm-github-deploy`,
listing exactly the same actions. Effective permissions are the intersection of
policy and boundary, so attaching another policy to this role later — by hand or
in a future stack edit — still cannot grant `iam:*`, `cloudformation:*`, `ec2:*`,
`rds:*`, `secretsmanager:*` or anything else. Widening CI access means editing
the boundary too, which shows up in review.

`ecs:UpdateService` is the one mutating call the pipeline needs
(`--force-new-deployment`). IAM has no condition key to narrow it to that flag,
so it stays scoped by resource to the four esm services.

The trust policy is exact-match on all of:

- `aud` = `sts.amazonaws.com`
- `repository` = `siliconii-vibe/esm-order-review`, plus the immutable
  `repository_id` / `repository_owner_id` (a rename keeps working; a
  deleted-and-recreated repo of the same name does not)
- `sub` = `repo:<repo>:ref:refs/heads/develop` or `.../main` — no other branch,
  no tag, no pull_request context
- `job_workflow_ref` = `<repo>/.github/workflows/deploy.yml@refs/heads/{develop,main}`
  — a newly added workflow file gets no credentials, even on `main`

Session duration is capped at 1 hour.

ECR repos (created by `esm-cicd`): `sk-{dev,prd}-an2-ecr-esm-{backend,frontend}`.

## Attaching your domain (prd)

1. Point DNS at the ALB (`AlbUrl` output).
2. Add an HTTPS listener + ACM cert (extend `esm-stack.ts`), or front it with
   CloudFront.
3. Set the real origin so CORS accepts it:
   `cdk deploy esm-prd -c prdOrigins=https://your-domain` (ALB DNS stays allowed).

## Naming convention

All resources use `sk-<env>-an2-<type>-esm` (e.g. `sk-dev-an2-alb-esm`,
`sk-prd-an2-ecs-cls-esm`, `sk-<env>-an2-ecr-esm-{backend,frontend}`). Deploy role:
`sk-an2-role-esm-github-deploy`. Log group: `/ecs/sk-<env>-an2-esm`. The `EsmStack`
helper `n(type)` builds these names.

## Before prd go-live — rotate the temp login hashes

`esm-prd` (`APP_ENV=production`) requires all nine login hashes non-empty. It was
seeded at create with a **temp password** so the service boots. Rotate to real
hashes (they survive infra deploys — the secret uses create-only
`generateSecretString`):

```bash
# generate each hash, then put the full JSON back:
python -m backend.scripts.generate_password_hash   # per account
aws secretsmanager put-secret-value --secret-id sk-prd-an2-sm-esm-app \
  --secret-string '{"AUTH_ADMINMASTER_PASSWORD_HASH":"...", ...9 keys...}'
aws ecs update-service --cluster sk-prd-an2-ecs-cls-esm \
  --service sk-prd-an2-ecs-svc-esm --force-new-deployment
```

## Subnet placement (pinned to sk-vibe-vpc-workload groups)

- ALB → `pub-web` (Public)
- Fargate service → `priv-app` (Private, NAT egress — pulls from ECR)
- RDS → `iso-db` (Isolated)

Change these group names in `esm-stack.ts` if you retarget another VPC.

## Assumptions / knobs

- Trust conditions are pinned to this repo's numeric ids and to
  `deploy.yml`; renaming the workflow file requires updating `cicd-stack.ts`.
- `-c vpcId=...` overrides the VPC; `CDK_DEFAULT_REGION` overrides the region.
