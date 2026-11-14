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

- 차트에는 비밀 값이 없어요. `existingSecret`에 미리 만든 Secret의 **이름**만 적어요.
- 로컬은 `webapp/.env`(커밋하지 않음)를 쓰고, 예시는 `webapp/.env.example`이에요.
- 쿠키에 `Secure`가 붙어 있어서 로그인 유지는 `https://`나 `http://localhost`에서만 돼요.

## 1. 이미지 만들기

저장소 루트에서 실행해요.

```bash
# 로컬 확인 (compose). 먼저 webapp/.env를 만들어요: cp webapp/.env.example webapp/.env
docker compose up --build        # http://localhost:8080

# 클러스터용 arm64 이미지를 레지스트리에 올려요 (ghcr.io 예시)
# GHCR는 fine-grained 토큰을 지원하지 않아요. classic 토큰에 write:packages 하나만 주세요(만료 7일 권장).
# 토큰은 화면과 셸 기록에 남지 않게 표준입력으로만 넘겨요. 예: .env의 GHCR_TOKEN
printf '%s' "$(grep -m1 '^GHCR_TOKEN=' .env | cut -d= -f2-)" | docker login ghcr.io -u jyje --password-stdin
docker buildx build --platform linux/arm64 -f docker/Dockerfile \
  -t ghcr.io/jyje/open-attendee:0.1.1 --push .
# 이미 arm64 머신에서 빌드한 이미지가 있으면 태그만 붙여서 올려도 돼요:
#   docker tag open-attendee:dev ghcr.io/jyje/open-attendee:0.1.1 && docker push ghcr.io/jyje/open-attendee:0.1.1
```

처음 올린 패키지는 비공개예요. 클러스터가 pull secret 없이 받으려면 GitHub의 패키지 설정(Package settings → Danger Zone → Change visibility)에서 **Public**으로 바꿔요. 이 이미지에는 비밀이 들어 있지 않아요(`.dockerignore`가 `.env`를 막아요).

비공개로 두려면 `read:packages` 토큰으로 pull secret을 만들고 `--set imagePullSecrets[0].name=ghcr-pull`로 넘겨요.

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

```bash
helm upgrade --install open-attendee ./helm \
  --kube-context microk8s -n open-attendee \
  --set image.tag=0.1.1

kubectl --context microk8s -n open-attendee rollout status deploy/open-attendee
kubectl --context microk8s -n open-attendee port-forward svc/open-attendee 8080:80   # http://localhost:8080
```

도메인과 HTTPS가 준비되면 인그레스를 켜요. 이 클러스터에는 `nginx` 인그레스 클래스와 `nginx-letsencrypt-prod` ClusterIssuer가 있어요.

```bash
helm upgrade --install open-attendee ./helm --kube-context microk8s -n open-attendee \
  --set image.tag=0.1.1 --set ingress.enabled=true --set ingress.host=<도메인>
```

## 4. 확인과 되돌리기

```bash
kubectl --context microk8s -n open-attendee get pods,pvc
kubectl --context microk8s -n open-attendee logs deploy/open-attendee --tail=50
curl -s http://localhost:8080/healthz       # port-forward 중에
helm rollback open-attendee --kube-context microk8s -n open-attendee
```

- 데이터 볼륨(PVC)에는 `helm.sh/resource-policy: keep`을 붙여서 `helm uninstall`을 해도 기록이 남아요.
- 복제본은 1개로 고정이에요. SQLite와 업로드 파일이 같은 볼륨 하나를 쓰기 때문이에요.
