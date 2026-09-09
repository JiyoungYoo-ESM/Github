# 배포 Runbook — ElastiCache Redis + Celery Worker

대상 변경: `esm-stack.ts`(Redis + 워커 서비스), `cicd-stack.ts`(워커 배포 권한),
`.github/deploy.sh`(워커 재배포). 예상 소요: 스택당 10~15분 (Redis 신규 생성 5~10분 포함).

## 0. 사전 확인

```bash
# 이 계정/프로필로 작업 (계정 634236767858)
export AWS_PROFILE=stylekorean-mkt
aws sts get-caller-identity   # Account가 634236767858인지 확인

# 진행 중인 스택 업데이트가 없는지 확인 — 전부 *_COMPLETE 여야 함
aws cloudformation describe-stacks --region ap-northeast-2 \
  --query "Stacks[?contains(StackName,'esm')].[StackName,StackStatus]" --output table

# 작업 트리 확인 후 커밋 · push (infra 변경은 main 머지 후 배포)
git status --short --branch
```

`UPDATE_IN_PROGRESS`인 스택이 있으면 끝날 때까지 대기.

## 1. 배포 순서 (반드시 이 순서대로)

| 순서 | 스택 | 이유 |
|---|---|---|
| 1 | `esm-cicd` | 배포 롤(ECR/ECS 권한) 갱신. 앱 파이프라인이 먼저 돌면 권한 오류로 실패 |
| 2 | `esm-dev` | Redis + 워커 생성, 웹 태스크에 REDIS_URL 주입 |
| 3 | — | **dev 검증 (아래 2번) 통과 후에만 진행** |
| 4 | `esm-prd` | dev와 동일 변경 |

이미지 재빌드 불필요 — celery는 backend 이미지에 이미 포함, 워커는 `:latest` 참조.

### 로컬 cdk 배포 (유일한 경로 — admin/SSO 필요)

GitHub Actions에는 cdk 권한이 없다. 인프라 배포는 계정 `634236767858`에 대한
admin/SSO를 가진 사람이 로컬에서만 수행한다. (main 머지 후 진행)

```bash
export AWS_PROFILE=stylekorean-mkt
aws sso login                          # 세션 만료 시
cd infra && npm ci

# 배포 전 diff로 변경 리소스 확인 (Redis/워커 추가 + 웹 태스크 교체만 나와야 정상)
npx cdk diff esm-dev

npx cdk deploy esm-cicd --require-approval never
npx cdk deploy esm-dev  --require-approval never
# ── 아래 2번 검증 통과 후 ──
npx cdk deploy esm-prd  --require-approval never
```

각 deploy는 CloudFormation 완료까지 대기 후 종료한다(esm-dev/prd는 Redis 신규
생성 때문에 10~15분). 실패 시 자동 롤백되고 명령이 비정상 종료로 끝난다.

## 2. 배포 후 검증 (dev 기준, prd는 dev→prd 치환)

```bash
# Redis 생성 확인 (available)
aws elasticache describe-cache-clusters --region ap-northeast-2 \
  --cache-cluster-id sk-dev-an2-ec-esm --query 'CacheClusters[0].CacheClusterStatus'

# 워커 서비스 기동 확인 (prd는 runningCount/desiredCount 2, dev는 1)
aws ecs describe-services --region ap-northeast-2 \
  --cluster sk-dev-an2-ecs-cls-esm --services sk-dev-an2-ecs-svc-worker-esm \
  --query 'services[0].[status,runningCount,desiredCount]'

# 워커 로그에서 브로커 접속 확인 — "celery@... ready" 가 보여야 함
aws logs tail /ecs/sk-dev-an2-esm --region ap-northeast-2 \
  --log-stream-name-prefix worker --since 10m
```

기능 검증 (화면):

1. `esm-dev.siliconii.com` 로그인 → CMS 분석 1건 실행.
2. 분석이 **완료 상태까지 도달**하는지 확인 (큐에 들어가고 안 돌면 워커 문제).
3. 워커 로그에 `Task analysis.cms ... received` / `succeeded` 확인.

## 3. 이상 시 대응

| 증상 | 원인/조치 |
|---|---|
| 분석이 "대기/실행 중"에서 안 움직임 | 워커가 죽었거나 브로커 접속 실패. 워커 로그 확인 → 워커만 재기동: `aws ecs update-service --cluster sk-dev-an2-ecs-cls-esm --service sk-dev-an2-ecs-svc-worker-esm --force-new-deployment` |
| 워커 로그에 Redis 연결 오류 | Redis 상태(available)와 SG 확인. `sk-dev-an2-sg-esm-redis`가 svc SG의 6379 인바운드를 허용해야 함 |
| Spot 중단으로 분석이 중간에 끊김 | 정상 동작 — visibility timeout(최대 60분) 후 자동 재실행. 잦으면 워커를 온디맨드로 전환 검토 |
| CFN 스택 롤백 | circuit breaker가 웹 서비스는 자동 롤백. 원인 해결 후 재배포 |

## 4. 롤백 (전체 되돌리기)

임시 조치로 워커만 끄면 **안 됨** — 웹에 REDIS_URL이 남아 있으면 분석이 큐에만
쌓이고 실행되지 않는다. 되돌릴 때는 코드째 되돌린다:

```bash
git revert <이번 배포 커밋>   # 머지 후
# 로컬에서 esm-dev(필요시 esm-prd) 재배포 → 웹이 in-process 분석으로 복귀
npx cdk deploy esm-dev --require-approval never
```

Redis 클러스터는 removal policy가 없어 스택에서 빠지면 삭제된다(상태 데이터는
휘발성이므로 손실 무방).

## 5. 스케일 업 (추후)

`esm-stack.ts`의 `cacheNodeType: 'cache.t4g.micro'` 값 변경 → 해당 스택 재배포.
노드 타입 변경 시 짧은 중단 발생(업무 시간 외 권장). 워커 처리량 부족 시
`Worker` 서비스는 운영에서 기본 2개, 개발에서 1개다. 처리량을 더 늘릴 때는
한 컨테이너의 동시 실행 수보다 `desiredCount`를 올려 수평 확장한다.
