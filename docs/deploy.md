# 배포 가이드 (microk8s)

대상 클러스터는 kubectl 컨텍스트 `microk8s`예요. 노드는 모두 arm64(Raspberry Pi)라서 이미지는 `linux/arm64`로 빌드해요.
`kubectl`과 `helm`은 항상 `--context microk8s`를 붙여서 다른 클러스터에 배포하지 않게 해요.

## 환경 변수와 Secret

| 구분 | 변수 | 어디에 두나 | 비고 |
|---|---|---|---|
| 비밀 (필수) | `OWNER_PASSWORD_HASH` | Secret | argon2 해시. 비밀번호 원문은 어디에도 저장하지 않아요 |
| 비밀 (필수) | `SESSION_SECRET` | Secret | 쿠키 서명 키. 바꾸면 모두 로그아웃돼요 |
| 비밀 (선택) | `OPENAI_API_KEY` 또는 `AWS_BEARER_TOKEN_BEDROCK` | Secret | AI 요약 단계부터 필요해요 |
| 설정 | `PROVIDER`, `AWS_REGION`, `BLOB_BACKEND`, `FEATURE_RECORDING`, `TRANSCRIBER` | ConfigMap (`values.yaml`의 `config`) | 비밀이 아니에요 |
| 설정 | `SQLITE_JOURNAL_MODE` | ConfigMap | 이 클러스터는 NFS라서 `delete`예요. 로컬 디스크는 `wal` |
| 고정 | `DATA_DIR=/data` | ConfigMap | PVC가 `/data`에 붙어요 |
| 설정 | `FORWARDED_ALLOW_IPS` | ConfigMap | `*`. 인그레스 뒤에서 로그인 제한이 접속자 IP별로 걸리게 해요 |

- 차트에는 비밀 값이 없어요. `existingSecret`에 미리 만든 Secret의 **이름**만 적어요.
- 로컬은 `webapp/.env`(커밋하지 않음)를 쓰고, 예시는 `webapp/.env.example`이에요.
- 쿠키에 `Secure`가 붙어 있어서 로그인 유지는 `https://`나 `http://localhost`에서만 돼요.

### S3 첨부 저장소

기본값은 `BLOB_BACKEND=local`이에요. 새 환경에서 S3를 사용하려면 버킷을 준비하고 Helm의 `config`에 아래 값을 넣어요.

```yaml
config:
  BLOB_BACKEND: s3
  S3_BUCKET: open-attendee-attachments
  AWS_REGION: ap-northeast-2
  # S3 호환 서비스의 경우에만 지정해요.
  # S3_ENDPOINT_URL: https://object-storage.example.com
```

Boto3의 기본 자격 증명 체인을 사용해요. 워크로드에 IAM 역할을 연결하거나, 액세스 키를 사용하는 환경에서는 `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`와 필요한 경우 `AWS_SESSION_TOKEN`을 기존 Secret에 넣어요. 권한은 버킷의 `s3:ListBucket`과 첨부 키의 `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`가 필요해요.

SQLite는 계속 `DATA_DIR`의 PVC에 기록해요. 기존 배포에서 저장소를 전환할 때는 먼저 기존 첨부의 키 구조를 유지해 새 저장소로 복사해야 해요. 버전 관리가 켜진 버킷은 삭제된 객체의 이전 버전을 보존하므로, 실제 보존 기간은 버킷의 수명 주기 정책에서 관리해요.

## 1. 이미지 (CI가 만들어요)

`main`에 머지되면 GitHub Actions의 **Build and push app image**(`.github/workflows/build.yml`)가 amd64와 arm64 이미지를 네이티브 러너에서 각각 빌드하고, 하나의 멀티 아키텍처 태그로 묶어 브랜치에 따라 `ghcr.io/jyje/open-attendee-dev`(main, dev), `-stg`(stg), `ghcr.io/jyje/open-attendee`(prd)에 올려요. 방식은 `jyje/mungchilog`의 `build.yml`을 따랐어요.

- 태그는 **`r<실행번호>-<커밋 7자리>`** 처럼 바뀌지 않는 값이에요. `latest` 같은 움직이는 태그는 없어요.
- 실행이 끝나면 **Actions → 해당 실행 → Summary**에 이 태그와 배포 명령이 나와요.
- PR에서는 빌드만 검증하고 올리지 않아요. `main` 푸시와 수동 실행(main 브랜치)만 올려요.
- 인증은 워크플로의 `GITHUB_TOKEN`이라서 개인 토큰이 필요 없어요. 패키지는 저장소가 공개라서 공개로 만들어져요. 처음 올라온 뒤 패키지가 비공개로 보이면 GitHub의 Package settings에서 Public으로 바꿔요.
- 테스트는 `ci.yml`(ruff, pytest, vue-tsc, helm lint)이 PR과 `main`에서 돌아요.

로컬에서 먼저 확인하고 싶을 때만 아래를 써요.

```bash
# 로컬 확인 (compose). 먼저 webapp/.env를 만들어요: cp webapp/.env.example webapp/.env
docker compose up --build        # http://localhost:8080
```

CI를 쓰지 않고 손으로 올려야 할 때는 `docker buildx build --platform linux/arm64 -f docker/Dockerfile -t ghcr.io/jyje/open-attendee-dev:<태그> --push .`를 써요. 이때 GHCR는 fine-grained 토큰을 받지 않아서 `write:packages`만 준 classic 토큰이 필요해요.

## 2. Secret 만들기 (한 번만)

비밀번호와 키가 셸 기록에 남지 않게 입력을 직접 받아요. 값은 이 터미널에서만 쓰고 바로 지워요.

```bash
read -rsp "소유자 비밀번호: " PW; echo
HASH=$(printf '%s' "$PW" | uv run --project webapp/src python -c \
  "import sys; from argon2 import PasswordHasher; print(PasswordHasher().hash(sys.stdin.read()))")

kubectl --context microk8s create namespace open-attendee
kubectl --context microk8s -n open-attendee create secret generic open-attendee \
  --from-literal=OWNER_PASSWORD_HASH="$HASH" \
  --from-literal=SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
unset PW HASH
```

AI 요약용 키는 나중에 `kubectl ... patch secret` 또는 `kubectl ... create secret ... --dry-run=client -o yaml | kubectl apply -f -`로 더해요.

## 3. 배포

브랜치와 같은 환경의 값 파일을 골라 CI Summary의 불변 이미지 태그와 함께 지정해요.

| 브랜치 | Helm 값 파일 | GHCR 이미지 |
|---|---|---|
| `main`, `dev` | `helm/values-dev.yaml` | `ghcr.io/jyje/open-attendee-dev` |
| `stg` | `helm/values-stg.yaml` | `ghcr.io/jyje/open-attendee-stg` |
| `prd` | `helm/values-prd.yaml` | `ghcr.io/jyje/open-attendee` |

아래는 개발 배포 예시예요. 여러 환경을 같은 클러스터에 두면 환경별 네임스페이스를 사용하고 각 네임스페이스에 Secret을 준비해요.

```bash
helm upgrade --install open-attendee ./helm \
  --kube-context microk8s -n open-attendee \
  -f helm/values-dev.yaml \
  --set image.tag=<CI가 만든 태그, 예: r12-abc1234>

kubectl --context microk8s -n open-attendee rollout status deploy/open-attendee
kubectl --context microk8s -n open-attendee port-forward svc/open-attendee 8080:80   # http://localhost:8080
```

도메인과 HTTPS가 준비되면 인그레스를 켜요. 이 클러스터에는 `nginx` 인그레스 클래스와 `nginx-letsencrypt-prod` ClusterIssuer가 있어요.

```bash
helm upgrade --install open-attendee ./helm --kube-context microk8s -n open-attendee \
  -f helm/values-dev.yaml --set image.tag=<태그> --set ingress.enabled=true --set ingress.host=<도메인>
```

## 4. 확인과 되돌리기

포트 포워딩한 앱은 저장소 루트에서 다음 명령으로 확인해요. 인그레스를 쓰면 끝에 앱의 HTTPS 주소를 넣어요.

```bash
uv run --frozen --project webapp/src python -m open_attendee.status http://127.0.0.1:8080
```

명령은 `/healthz`에서 SQLite 준비 상태, LLM 설정, 첨부 저장소 종류를 조회해 JSON으로 표시해요. 준비되면 종료 코드 0을, 준비되지 않았거나 조회에 실패하면 1을 반환해요. LLM 설정 정보와 저장소 종류는 연결 상태 점검과 별개예요.

```bash
kubectl --context microk8s -n open-attendee get pods,pvc
kubectl --context microk8s -n open-attendee logs deploy/open-attendee --tail=50
curl -s http://localhost:8080/healthz       # port-forward 중에
helm rollback open-attendee --kube-context microk8s -n open-attendee
```

- 데이터 볼륨(PVC)에는 `helm.sh/resource-policy: keep`을 붙여서 `helm uninstall`을 해도 기록이 남아요.
- 복제본은 1개로 고정이에요. SQLite가 PVC 하나에 기록되기 때문이에요.
