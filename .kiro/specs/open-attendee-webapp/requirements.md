# Requirements Document

> **변경 메모 (2026-11-14):** 화면은 Jinja2와 HTMX 대신 **Vue 3 + Vite**(`webapp/frontend/`)로 만들고, 서버는 `/api/...` JSON API만 낸다. 빌드된 화면(`frontend/dist`)은 FastAPI가 서빙한다. 아래 본문에서 Jinja2, HTMX, "서버 렌더링 화면"을 말하는 부분은 이 결정으로 대체된다(본문은 리뷰 때 함께 고친다). 배포는 `docker/Dockerfile`(다단계), `docker-compose.yml`, `helm/`이고 클러스터의 기본 저장소가 NFS라서 `SQLITE_JOURNAL_MODE=delete`를 쓴다(요구사항 27.9의 WAL은 기본값으로만 남는다). 자세한 내용은 `docs/deploy.md`.

## Introduction

이 문서는 `design.md`(Open Attendee 웹앱 설계 초안)에서 요구사항을 뽑아 정리한 것입니다. Open Attendee는 밋업, 학회, 이벤트, 미팅에 참석한 사람이 필기, 사진, 발표자료, 참고자료, 동의된 녹음을 한 세션에 모으고, AI가 출처가 붙은 초안을 만들면 사람이 검토하고 승인한 뒤 내보내는 웹앱입니다.

### 단계 표기

요구사항마다 **단계** 줄을 둡니다. 한 요구사항 안에서 단계가 다른 항목은 항목 앞에 단계를 따로 적습니다.

| 표기 | 뜻 |
|---|---|
| 0단계 | 해커톤 데모 (2026-11-14 18:00 제출). "출처가 붙은 초안을 사람이 검토하고 내보내는 흐름" 하나를 끝까지 보여 줌 |
| 1단계 | MVP. 녹음, 전사, 얼굴 흐림, PPTX, 템플릿 복제와 수정, 자동 요약, HTML 내보내기 |
| 2단계 | 이후 단계. 이 문서에는 범위 밖 목록으로만 적음 |

EARS 문장에서 "WHERE 0단계 구성이면", "WHERE 1단계 이후 구성이면"은 해당 단계의 빌드와 설정에서만 적용된다는 뜻입니다.

### 가정 (확정 사항이 아님)

아래 항목은 사용자가 아직 정하지 않았습니다. 설계가 임시로 고른 기본값을 요구사항에 반영했고, 값이 바뀌면 괄호 안의 요구사항을 고칩니다.

| 번호 | 가정 (임시 기본값) | 영향받는 요구사항 |
|---|---|---|
| A1 | 소유자 1명만 씁니다. 모든 데이터에 `owner_id`를 둡니다. | 25, 26 |
| A2 | AWS 리전은 `provider-manager` 기본값(`us-east-1`)을 따르고 GPU를 쓰지 않습니다. | 27 |
| A3 | 온프레미스(Raspberry Pi MicroK8s)에는 GPU가 없어서 전사를 돌리지 않습니다. | 12, 27 |
| A4 | LLM 추론은 Bedrock 또는 OpenAI API 키로만 합니다. Codex 구독은 추론에 쓰지 않습니다. | 15 |
| A5 | 0단계에서 녹음 업로드는 끕니다(`FEATURE_RECORDING=false`). 동의 게이트는 0단계부터 구현합니다. | 9, 10, 11 |
| A6 | 블로그와 링크드인 템플릿을 둘 다 내장하고, 데모는 블로그로 시연합니다. | 21 |
| A7 | "필기 20장 이상"은 세션당 사진과 메모를 20개 넘게 지원한다는 뜻으로 보고, 사진 상한을 200장으로 둡니다. | 3 |
| A8 | 내보내기는 마크다운과 클립보드 복사로 시작합니다. | 24 |
| A9 | 앱 코드는 이 저장소의 `webapp/`에 둡니다. 기획 문서 9절과 충돌하므로 확인이 필요합니다. | 27 |

### 열린 결정

설계 문서 "열린 결정" 절의 11개 항목(사용 대상, AWS 계정과 GPU, 온프레미스 GPU, AI 구독 사용, 녹음 포함 여부, 첫 산출물, "20장"의 뜻, 내보내기 형식, 코드 위치, 보관 기간, 법률 검토)은 아직 결정되지 않았습니다. 이 문서는 위 가정 표의 기본값으로 쓰였습니다. 보관 기간(열린 결정 10)은 "사용자가 지울 때까지 보관"을 임시 기본값으로 둡니다. 법률 검토(열린 결정 11)가 끝나기 전까지 녹음 기능은 동의 게이트 뒤에만 둡니다.

### 범위 밖 (2단계 이후)

손글씨 입력, 비전 모델로 사진 내용 해석과 연결, 참고자료 URL 가져오기(안전 조건만 요구사항 7에 적음), 스트리밍 요약, 화자 분리, 대학 과제와 출장 보고서 템플릿, DOCX와 PDF 내보내기, 여러 사용자와 공유, 스캔 PDF OCR, AWS GPU 전사 워커.

## Glossary

- **Open_Attendee**: 이 문서가 다루는 웹앱 전체. FastAPI 서비스 하나와 그 컨테이너 이미지
- **Owner**: 앱을 쓰는 소유자 1명 `[가정 A1]`
- **Web_UI**: Jinja2와 HTMX로 만든 서버 렌더링 화면. 녹음만 브라우저 MediaRecorder를 씀
- **Auth**: 소유자 로그인, 세션 쿠키, CSRF 검사, 로그인 시도 제한을 맡는 구성 요소
- **Event_Session**: 행사 하나의 기록 묶음. 메모 블록, 자료, 동의 기록, 요약, 초안을 가짐
- **Session_Service**: 세션과 메모 블록을 만들고, 고치고, 지우는 구성 요소
- **Memo_Block**: 메모 편집기의 블록 하나. 클라이언트가 만든 UUID를 ID로 쓰고 저장할 때마다 `revision`이 1 오름
- **Asset**: 세션에 올린 자료 하나. 종류는 `photo`, `slides`, `reference`, `voice_memo`, `recording`
- **Asset_Service**: 업로드를 검사하고 저장하고 지우는 구성 요소
- **Blob_Store**: 파일 저장소 인터페이스. 로컬 볼륨 구현이 기본이고 S3 구현을 더함
- **Photo_Processor**: 사진의 EXIF 제거, 축소, 얼굴 흐림, 메모 연결을 맡는 구성 요소
- **Doc_Extractor**: PDF, PPTX, TXT, MD에서 텍스트를 뽑아 `Doc_Chunk`로 나누는 구성 요소
- **Doc_Chunk**: 발표자료나 참고자료의 한 쪽(또는 슬라이드)을 `MAX_CHUNK_CHARS` 이하로 나눈 텍스트 조각
- **Consent_Record**: 녹음 동의 기록. 세 체크 항목(`informed_all`, `can_document`, `no_outside_disclosure`), 동의 날짜, 동의 방법, 철회 시각을 가짐
- **Consent_Gate**: 동의가 필요한 자료인지 판정하고 유효한 동의 기록을 요구하는 구성 요소
- **Consent_Required_Asset**: `kind=recording`인 자료, 또는 `solo_voice=False`인 `voice_memo` 자료
- **Job_Queue**: DB 테이블로 만든 작업 큐. 작업 종류는 `SUMMARY`, `DRAFT`, `PHOTO`, `DOC`, `TRANSCRIBE`
- **Worker**: 같은 프로세스에서 작업 큐의 작업을 꺼내 실행하고 SSE 이벤트를 보내는 백그라운드 작업
- **Transcriber**: 오디오를 전사 구간(`TranscriptSegment`)으로 바꾸는 구성 요소. 구현은 `fake`, `faster_whisper`, `remote`
- **LLM_Gateway**: `provider-manager`의 `Provider`를 감싸서 JSON 응답 검증, 재질문, 로그 마스킹을 맡는 구성 요소
- **Pipeline**: LangGraph로 조립한 초안 생성 흐름(`collect_sources` → `extract_facts` → `compose_draft` → `verify_draft`)과 요약 생성
- **Source_Map**: 출처 라벨(`S1`, `S2`, ...)과 실제 출처(`Source_Ref`)의 대응표. 서버에만 둠
- **Source_Ref**: 출처 하나. 종류(memo, transcript, photo, doc, reference), 대상 ID, 메모 블록의 당시 `revision`, 사람이 읽는 위치(`locator`)를 가짐
- **Fact**: 출처에서 뽑은 사실 하나. 출처를 하나 이상 가짐
- **Fact_Extractor**: 출처 대응표로 LLM에 사실 추출을 맡기고 결과를 걸러 내는 구성 요소
- **Draft**: 템플릿에 따라 만든 초안. 상태는 `generating`, `in_review`, `approved`, `failed`
- **Sentence**: 초안의 문장 하나. 출신(`origin`)은 `ai`, `ai_edited`, `user_insight`. 검증 상태는 `verified`, `unverified`, `kept_as_opinion`, `n/a`
- **Draft_Composer**: 템플릿과 사실 목록으로 초안 문장을 만드는 구성 요소
- **Verifier**: 초안 문장의 구조 검사와 지지 판정을 해서 검증 상태를 정하는 구성 요소
- **Unverified_Sentence**: `verify_status=unverified`인 문장. 화면에 "미검증"으로 표시함
- **Template**: 섹션 목록으로 된 산출물 틀. 섹션마다 제목, 작성 지시, 최대 문장 수, 인사이트 자리 여부가 있음
- **Template_Service**: 템플릿 목록, 복제, 저장을 맡는 구성 요소
- **Template_Parser**: 내장 템플릿 TOML 파일과 `template_snapshot` JSON을 `Template` 객체로 읽는 구성 요소
- **Template_Serializer**: `Template` 객체를 `template_snapshot` JSON으로 쓰는 구성 요소
- **Review_Service**: 인사이트 추가, 문장 수정, 미검증 처리, 사진 확인, 승인을 맡는 구성 요소
- **Exporter**: 승인된 초안을 마크다운(1단계는 HTML도) 결과물로 바꾸는 구성 요소
- **Live_Summary**: 행사 중에 만드는 준실시간 요약. 항목마다 출처를 가짐
- **Summary_Scheduler**: 메모 블록 저장 시 요약 갱신 여부를 정하는 함수 `should_refresh_summary` (1단계)
- **Deployment_Package**: 컨테이너 이미지(`docker/Dockerfile`)와 helm 차트(`helm/`)
- **Feature_Flag_Recording**: 환경 변수 `FEATURE_RECORDING`. 녹음 업로드 사용 여부

## Requirements

### Requirement 1: 세션 관리

**User Story:** As a 행사 참석자, I want 행사마다 세션을 만들고 목록에서 고르기를, so that 한 행사의 기록을 한 곳에 모을 수 있다.

**단계:** 0단계

#### Acceptance Criteria

1. WHEN Owner가 1~200자 제목으로 세션 만들기를 요청하면, THE Session_Service SHALL 새 Event_Session을 만들어 세션 목록에 넣는다.
2. IF 세션 제목이 비어 있거나 200자를 넘으면, THEN THE Session_Service SHALL 세션을 만들지 않고 검증 오류를 돌려준다.
3. THE Web_UI SHALL 세션 목록에 행사 이름, 날짜, 자료 수, 초안 상태를 보여 준다.
4. WHEN Owner가 세션 제목이나 날짜 수정을 요청하면, THE Session_Service SHALL 변경을 저장하고 `updated_at`을 갱신한다.
5. WHEN Owner가 세션 삭제를 요청하면, THE Session_Service SHALL 세션에 속한 모든 DB 행과 Blob_Store의 모든 파일을 삭제한다.

### Requirement 2: 메모 편집기

**User Story:** As a 행사 참석자, I want 블록 단위로 메모를 쓰기를, so that 행사 중에 끊김 없이 필기하고 각 메모를 출처로 쓸 수 있다.

**단계:** 0단계 (손글씨 입력은 2단계)

#### Acceptance Criteria

1. WHEN Owner가 메모 블록을 처음 저장하면, THE Session_Service SHALL 클라이언트가 만든 UUID를 Memo_Block ID로 쓰고 `revision`을 1로 저장한다.
2. WHEN Owner가 이미 있는 메모 블록을 다시 저장하면, THE Session_Service SHALL 해당 Memo_Block의 `revision`을 정확히 1 올린다.
3. IF 메모 블록 텍스트가 10,000자를 넘으면, THEN THE Session_Service SHALL 저장을 거부하고 검증 오류를 돌려준다.
4. WHEN Owner가 메모 블록 삭제를 요청하면, THE Session_Service SHALL 해당 Memo_Block을 삭제한다.
5. THE Session_Service SHALL 세션당 메모 블록을 20개 넘게 저장할 수 있게 한다. `[가정 A7]`
6. WHILE 화면 폭이 design-system의 모바일 기준 폭 이하이면, THE Web_UI SHALL 메모 입력창과 사진 촬영 버튼을 화면 아래쪽에 둔다.
7. THE Web_UI SHALL `design-system/tokens.css`의 토큰과 `design-system/DESIGN.md`의 규칙을 따르고, `prefers-reduced-motion` 설정이 켜져 있으면 움직임 효과를 끈다.

### Requirement 3: 사진 첨부와 EXIF 제거

**User Story:** As a 행사 참석자, I want 슬라이드와 화이트보드 사진을 20장 넘게 올리기를, so that 필기로 놓친 내용을 사진으로 남기면서 위치 정보는 남기지 않을 수 있다.

**단계:** 0단계

#### Acceptance Criteria

1. THE Asset_Service SHALL 세션당 사진을 200장까지 받는다. `[가정 A7]`
2. IF 사진이 200장인 세션에 사진 업로드가 오면, THEN THE Asset_Service SHALL 413을 돌려주고 파일을 저장하지 않는다.
3. WHEN 사진이 업로드되면, THE Photo_Processor SHALL 촬영 시각(`DateTimeOriginal`)만 읽고 모든 EXIF를 지운 이미지를 저장 대상으로 넘긴다.
4. THE Asset_Service SHALL EXIF가 지워진 사진만 Blob_Store에 저장하고, 원본 사진 파일과 GPS 정보는 Blob_Store와 DB에 저장하지 않는다.
5. WHEN 사진이 업로드되면, THE Photo_Processor SHALL EXIF 회전 정보를 픽셀에 반영해 화면에 보이는 방향을 원본과 같게 유지한다.
6. WHEN HEIC 사진이 업로드되면, THE Photo_Processor SHALL 사진을 JPEG로 변환해 저장한다.
7. WHEN 사진이 업로드되면, THE Photo_Processor SHALL 사진을 긴 변 2048px 이하로 줄여 저장하고 긴 변 400px 축소판을 만든다.
8. IF 업로드한 사진 파일이 깨져 있으면, THEN THE Asset_Service SHALL 422와 이유를 돌려주고 파일을 저장하지 않는다.
9. WHEN Owner가 사진에 설명(caption)을 붙이면, THE Asset_Service SHALL 설명을 해당 Asset에 저장한다.

### Requirement 4: 얼굴 흐림과 사진 내보내기 제한

**User Story:** As a 행사 참석자, I want 다른 사람 얼굴이 담긴 사진이 그대로 공개되지 않기를, so that 참석자의 초상을 보호할 수 있다.

**단계:** 항목 1은 0단계, 항목 2~5는 1단계

#### Acceptance Criteria

1. WHERE 0단계 구성이면, THE Exporter SHALL 내보내기 결과에서 사진을 모두 빼고 사진은 초안의 근거로만 쓴다.
2. WHERE 1단계 이후 구성이면, WHEN 사진이 저장되면, THE Job_Queue SHALL 해당 사진의 `PHOTO` 작업을 등록한다.
3. WHERE 1단계 이후 구성이면, WHEN `PHOTO` 작업이 실행되면, THE Photo_Processor SHALL 검출한 얼굴 영역을 흐리게 하고 해당 Asset의 `faces_blurred`를 참으로 기록한다.
4. WHERE 1단계 이후 구성이면, WHEN Owner가 검토 화면에서 사진의 "얼굴 처리 확인"을 누르면, THE Review_Service SHALL 해당 Asset의 `face_check_confirmed`를 참으로 기록한다.
5. WHERE 1단계 이후 구성이면, THE Exporter SHALL `faces_blurred`와 `face_check_confirmed`가 모두 참인 사진만 내보내기 결과에 넣는다.

### Requirement 5: 사진과 메모 연결

**User Story:** As a 행사 참석자, I want 사진이 같은 시각의 메모에 자동으로 붙기를, so that 사진을 하나씩 정리하지 않아도 된다.

**단계:** 0단계 (이미지 내용 기준 연결은 2단계)

#### Acceptance Criteria

1. WHEN 사진 연결을 계산하면, THE Photo_Processor SHALL 사진마다 기준 시각과의 차이가 5분 이하인 Memo_Block 중 차이가 가장 작은 블록에 사진을 연결한다.
2. IF 기준 시각과의 차이가 5분 이하인 Memo_Block이 없으면, THEN THE Photo_Processor SHALL 해당 사진을 어느 블록에도 연결하지 않는다.
3. WHEN 시각 차이가 같은 Memo_Block이 둘 이상이면, THE Photo_Processor SHALL 작성 시각이 앞선 블록을 고른다.
4. IF 사진에 촬영 시각이 없으면, THEN THE Photo_Processor SHALL 업로드 시각을 기준 시각으로 쓴다.
5. THE Photo_Processor SHALL 모든 시각을 UTC로 정규화한 뒤 비교한다.
6. WHEN Owner가 화면에서 사진 연결을 바꾸면, THE Asset_Service SHALL Owner가 고른 연결을 저장하고, 이후 자동 연결 계산이 해당 사진의 연결을 덮어쓰지 않게 한다.

### Requirement 6: 발표자료 첨부와 텍스트 추출

**User Story:** As a 행사 참석자, I want 발표자료 PDF(이후 PPTX)를 올려 내용이 요약과 초안에 쓰이기를, so that 발표자료 내용을 손으로 옮겨 적지 않아도 된다.

**단계:** PDF는 0단계, PPTX는 1단계

#### Acceptance Criteria

1. WHEN PDF 발표자료가 업로드되면, THE Doc_Extractor SHALL 쪽 단위로 텍스트를 뽑아 1부터 쪽 번호를 붙인 Doc_Chunk로 저장한다.
2. WHEN 한 쪽의 텍스트가 `MAX_CHUNK_CHARS`를 넘으면, THE Doc_Extractor SHALL 해당 텍스트를 `MAX_CHUNK_CHARS` 이하 조각으로 나누고 0부터 조각 번호를 붙인다.
3. IF PDF에서 뽑은 텍스트가 비어 있으면, THEN THE Doc_Extractor SHALL 자료를 저장하고 "텍스트 없음" 상태를 Owner에게 표시한다.
4. IF 업로드한 PDF가 암호로 잠겨 있으면, THEN THE Asset_Service SHALL 422와 이유를 돌려준다.
5. THE Asset_Service SHALL 세션당 발표자료를 20개까지 받는다.
6. WHERE 0단계 구성이면, WHEN PPTX 발표자료가 업로드되면, THE Asset_Service SHALL 415와 함께 PDF로 변환해 올리라는 안내를 돌려준다.
7. WHERE 1단계 이후 구성이면, WHEN PPTX 발표자료가 업로드되면, THE Doc_Extractor SHALL 슬라이드 단위로 텍스트를 뽑아 1부터 슬라이드 번호를 붙인 Doc_Chunk로 저장한다.
8. WHEN 발표자료 텍스트 추출이 끝나면, THE Pipeline SHALL 다음 요약과 초안 생성에서 해당 Doc_Chunk를 출처로 포함한다.

### Requirement 7: 참고자료

**User Story:** As a 행사 참석자, I want 행사 관련 참고자료를 함께 올리기를, so that 초안이 행사 밖의 배경 자료도 근거로 쓸 수 있다.

**단계:** 파일 업로드는 0단계, URL 가져오기는 2단계

#### Acceptance Criteria

1. WHEN TXT, MD, PDF 참고자료가 업로드되면, THE Doc_Extractor SHALL 텍스트를 뽑아 `reference` 종류의 Doc_Chunk로 저장한다.
2. THE Asset_Service SHALL 세션당 참고자료를 50개까지 받는다.
3. WHERE 0단계 또는 1단계 구성이면, THE Asset_Service SHALL 참고자료를 파일 업로드로만 받는다.
4. WHERE 2단계 이후 구성이면, WHEN Owner가 URL 참고자료 가져오기를 요청하면, THE Asset_Service SHALL 사설 IP 대역과 클라우드 메타데이터 주소로 가는 요청을 거부하고 리디렉션을 따라가지 않는다.

### Requirement 8: 업로드 공통 검사와 저장

**User Story:** As a 운영자, I want 업로드가 형식과 크기 검사를 거쳐 안전한 경로에 저장되기를, so that 잘못된 파일이나 악성 파일 이름이 앱을 망가뜨리지 않는다.

**단계:** 0단계 (S3 백엔드는 1단계)

#### Acceptance Criteria

1. THE Asset_Service SHALL 파일 형식을 확장자가 아닌 파일 앞부분의 매직 바이트로 확인한다.
2. IF 매직 바이트가 자료 종류의 허용 형식(사진 JPEG, PNG, HEIC / 발표자료 PDF, PPTX / 참고자료 TXT, MD, PDF / 오디오 webm, m4a, mp3, wav)과 맞지 않으면, THEN THE Asset_Service SHALL 415를 돌려주고 파일을 저장하지 않는다.
3. IF 업로드 크기가 종류별 상한(사진 20MB, 발표자료 30MB, 참고자료 20MB, 음성 메모 50MB, 녹음 2GB)을 넘으면, THEN THE Asset_Service SHALL 413을 돌려주고 파일을 저장하지 않는다.
4. THE Asset_Service SHALL 파일을 `<owner>/<session>/<asset_uuid>` 형식의 키로 저장하고, 원래 파일 이름은 표시용으로 DB에만 둔다.
5. WHEN Open_Attendee가 저장된 파일을 응답으로 내보내면, THE Open_Attendee SHALL `Content-Disposition: attachment`와 `X-Content-Type-Options: nosniff` 헤더를 붙인다.
6. WHEN Owner가 자료 삭제를 요청하면, THE Asset_Service SHALL 해당 Asset의 DB 행, 파생 데이터(Doc_Chunk, 전사 구간), Blob_Store 파일을 함께 삭제한다.
7. IF Blob_Store 쓰기가 용량 부족으로 실패하면, THEN THE Asset_Service SHALL 507을 돌려준다.
8. THE Blob_Store SHALL 로컬 볼륨(`DATA_DIR`) 구현을 기본값으로 쓴다.
9. WHERE `BLOB_BACKEND`가 `s3`이면, THE Blob_Store SHALL 파일을 `S3_BUCKET`에 SSE-S3 서버 측 암호화로 저장한다.

### Requirement 9: 녹음 동의 기록

**User Story:** As a 행사 참석자, I want 녹음 전에 동의 확인 절차를 거치기를, so that 다른 사람의 목소리를 동의 없이 기록하지 않는다.

**단계:** 0단계 (데이터 모델과 서버 검사로 구현, 화면은 녹음 기능과 함께 1단계) `[가정 A5]`

#### Acceptance Criteria

1. WHEN Owner가 동의 양식을 제출하고 세 체크 항목(`informed_all`, `can_document`, `no_outside_disclosure`)이 모두 참이면, THE Consent_Gate SHALL Consent_Record를 만든다.
2. IF 동의 양식의 세 체크 항목 중 하나라도 거짓이면, THEN THE Consent_Gate SHALL Consent_Record를 만들지 않고 검증 오류를 돌려준다.
3. THE Consent_Gate SHALL 동의 날짜(`obtained_on`)와 동의 방법(`method`)을 Consent_Record에 함께 저장한다.
4. WHEN Owner가 동의 철회를 요청하면, THE Consent_Gate SHALL 해당 Consent_Record의 `revoked_at`에 철회 시각을 기록한다.
5. WHILE 동의 창의 세 체크 항목이 모두 체크되지 않은 동안, THE Web_UI SHALL 동의 창의 확인 버튼을 비활성으로 둔다.
6. THE Web_UI SHALL 동의 창에 기획 문서 5.3절의 경고 문구와 동의 날짜, 동의 방법 입력란을 보여 준다.

### Requirement 10: 서버가 강제하는 동의 게이트

**User Story:** As a 운영자, I want 동의 검사가 화면이 아니라 서버에서 강제되기를, so that API를 직접 불러도 동의 없는 녹음이 처리되지 않는다.

**단계:** 0단계

#### Acceptance Criteria

1. THE Consent_Gate SHALL `kind=recording`인 자료와 `solo_voice=False`인 `voice_memo` 자료를 Consent_Required_Asset으로 판정한다.
2. THE Consent_Gate SHALL `solo_voice=True`인 `voice_memo` 자료와 `photo`, `slides`, `reference` 자료를 동의가 필요 없는 자료로 판정한다.
3. THE Consent_Gate SHALL 같은 세션에 속하고, 철회되지 않았고, 세 체크 항목이 모두 참인 Consent_Record만 유효한 동의로 인정한다.
4. IF Consent_Required_Asset이 유효한 동의 없이 업로드되면, THEN THE Asset_Service SHALL 403을 돌려주고 파일을 저장하지 않는다.
5. IF 유효한 동의가 없는 Consent_Required_Asset으로 `TRANSCRIBE` 작업 등록이 요청되면, THEN THE Job_Queue SHALL 작업을 만들지 않고 `ConsentRequired` 오류를 낸다.
6. THE Job_Queue SHALL HTTP API를 거친 등록 요청과 `JobQueue.enqueue` 직접 호출에 같은 동의 검사를 적용한다.

### Requirement 11: 녹음 기능 플래그

**User Story:** As a 개발자, I want 녹음 기능을 설정으로 켜고 끄기를, so that 법률 검토 전인 데모에서는 녹음을 끄고 나중에 플래그만 켜면 된다.

**단계:** 0단계에서 끔, 1단계에서 켬 `[가정 A5]`

#### Acceptance Criteria

1. THE Open_Attendee SHALL Feature_Flag_Recording의 기본값을 `false`로 둔다.
2. WHILE Feature_Flag_Recording이 `false`이면, THE Web_UI SHALL 녹음 업로드 메뉴와 녹음 버튼을 숨긴다.
3. WHILE Feature_Flag_Recording이 `false`이거나 `TRANSCRIBER`가 `none`이면, THE Asset_Service SHALL `kind=recording` 업로드 요청에 503을 돌려준다.
4. WHERE 1단계 이후 구성이면, WHILE Feature_Flag_Recording이 `true`이면, THE Web_UI SHALL 동의 창을 거친 뒤 MediaRecorder로 녹음하고 업로드하는 기능을 제공한다.

### Requirement 12: 녹음 전사

**User Story:** As a 행사 참석자, I want 동의된 녹음이 타임스탬프가 붙은 텍스트로 바뀌기를, so that 발표 내용을 초안의 출처로 쓸 수 있다.

**단계:** 1단계 (화자 분리와 원격 GPU 전사는 2단계)

#### Acceptance Criteria

1. WHEN 유효한 동의가 있는 오디오 자료가 저장되면, THE Job_Queue SHALL 해당 자료의 `TRANSCRIBE` 작업을 등록한다.
2. WHEN `TRANSCRIBE` 작업이 실행되면, THE Transcriber SHALL 오디오를 10분 조각(겹침 5초)으로 나눠 전사하고, 각 구간에 조각 시작 시각을 더해 절대 타임스탬프로 바꾼다.
3. THE Transcriber SHALL 한 오디오 자료의 전사 구간을 시작 시각 순으로 돌려주고, 모든 구간이 `0 <= start_ms < end_ms <= 오디오 길이`를 만족하게 한다.
4. THE Transcriber SHALL `TRANSCRIBER` 설정값(`none`, `fake`, `faster_whisper`, `remote`)에 맞는 구현을 쓰고, 기본 전사 언어를 한국어(`ko`)로 둔다.
5. WHERE `TRANSCRIBER`가 `faster_whisper`이면, THE Transcriber SHALL `STT_MODEL` 환경 변수의 모델 크기(기본 `small`)를 쓴다.
6. WHEN 전사가 끝나면, THE Worker SHALL SSE로 `transcript.ready` 이벤트를 보낸다.

### Requirement 13: 전사 후 원본 음성 삭제

**User Story:** As a 행사 참석자, I want 전사가 끝나면 원본 음성이 기본으로 지워지기를, so that 필요 이상의 음성 데이터를 보관하지 않는다.

**단계:** 1단계

#### Acceptance Criteria

1. THE Session_Service SHALL 새 Event_Session의 `retain_audio` 기본값을 `false`로 둔다.
2. WHEN 전사가 성공하고 세션의 `retain_audio`가 `false`이면, THE Worker SHALL 원본 음성을 Blob_Store에서 지우고, Asset의 `blob_key`를 비우고, 상태를 `original_deleted`로 바꾼다.
3. WHEN 전사가 성공하고 세션의 `retain_audio`가 `true`이면, THE Worker SHALL 원본 음성을 보관하고 Asset 상태를 `ready`로 바꾼다.
4. IF 전사가 실패하면, THEN THE Worker SHALL 원본 음성을 지우지 않고 작업을 재시도 대상으로 돌린다.
5. IF 원본 음성 삭제가 실패하면, THEN THE Worker SHALL 작업을 실패로 처리해 재시도 대상으로 돌린다.
6. IF 같은 자료의 전사가 3회 실패하면, THEN THE Web_UI SHALL Owner에게 원본 음성 보관과 삭제 중 하나를 고르게 한다.

### Requirement 14: 동의 철회 처리

**User Story:** As a 녹음된 참석자를 대신하는 소유자, I want 동의를 철회하면 관련 데이터가 지워지기를, so that 철회된 동의로 만든 기록이 남지 않는다.

**단계:** 1단계

#### Acceptance Criteria

1. WHEN Consent_Record가 철회되면, THE Job_Queue SHALL 해당 기록에 묶인 자료의 `queued` 상태 `TRANSCRIBE` 작업을 취소한다.
2. WHEN Consent_Record가 철회되면, THE Asset_Service SHALL 해당 기록에 묶인 자료의 전사 구간과 원본 음성을 삭제한다.
3. WHEN 철회로 전사 구간이 삭제된 뒤 검증이 실행되면, THE Verifier SHALL 삭제된 전사 구간을 인용한 문장을 Unverified_Sentence로 바꾼다.

### Requirement 15: LLM 게이트웨이

**User Story:** As a 개발자, I want 모든 LLM 호출이 provider-manager를 거치는 한 통로로 가기를, so that 시크릿 관리, 응답 검증, 로그 마스킹을 한 곳에서 처리한다.

**단계:** 0단계

#### Acceptance Criteria

1. THE LLM_Gateway SHALL `provider-manager`의 `get_provider()`로 `PROVIDER` 환경 변수에 맞는 Bedrock 또는 OpenAI 제공자를 쓴다.
2. IF 선택된 제공자가 `codex`이면, THEN THE LLM_Gateway SHALL 생성을 거부하고 오류를 낸다. `[가정 A4]`
3. WHEN LLM 응답을 받으면, THE LLM_Gateway SHALL 응답 텍스트에서 첫 번째 JSON 객체를 꺼내 호출자가 지정한 스키마로 검증한다.
4. IF 응답의 JSON 추출이나 스키마 검증이 실패하면, THEN THE LLM_Gateway SHALL 오류 내용을 붙여 1회 다시 묻는다.
5. IF 재질문 뒤에도 JSON 추출이나 스키마 검증이 실패하면, THEN THE LLM_Gateway SHALL `LLMError`를 낸다.
6. THE LLM_Gateway SHALL 로그에 `provider.describe()` 결과, 작업 이름, 소요 시간, 입력과 출력 글자 수만 남긴다.
7. IF LLM 제공자가 HTTP 429를 돌려주면, THEN THE Job_Queue SHALL 해당 작업을 지수 백오프로 최대 3회 재시도한다.
8. IF LLM 제공자가 설정되지 않았으면, THEN THE Web_UI SHALL 초안 만들기 버튼을 비활성으로 둔다.
9. THE LLM_Gateway SHALL 생성자로 `Provider` 구현을 주입받아, 테스트에서 정해진 응답을 돌려주는 가짜 제공자를 쓸 수 있게 한다.

### Requirement 16: 준실시간 요약

**User Story:** As a 행사 참석자, I want 행사 중에 지금까지의 기록 요약을 보기를, so that 놓친 흐름을 바로 따라잡을 수 있다.

**단계:** 항목 1~4는 0단계(버튼), 항목 5~7은 1단계(자동 갱신), 스트리밍은 2단계

#### Acceptance Criteria

1. WHEN Owner가 "요약 새로고침"을 누르면, THE Job_Queue SHALL 해당 세션의 `SUMMARY` 작업 등록을 처리한다.
2. IF 같은 세션에 `queued` 또는 `running` 상태인 `SUMMARY` 작업이 있으면, THEN THE Job_Queue SHALL 새 작업을 만들지 않고 기존 작업을 돌려준다.
3. WHEN `SUMMARY` 작업이 끝나면, THE Worker SHALL 항목마다 Source_Ref가 붙은 Live_Summary를 저장하고 SSE로 `summary.updated` 이벤트를 보낸다.
4. THE Web_UI SHALL 기록 화면 옆 영역(모바일은 탭)에 최신 Live_Summary와 사진 연결 결과를 보여 준다.
5. WHERE 1단계 이후 구성이면, WHEN 메모 블록이 저장되면, THE Session_Service SHALL Summary_Scheduler가 참을 돌려줄 때만 `SUMMARY` 작업을 등록한다.
6. WHERE 1단계 이후 구성이면, THE Summary_Scheduler SHALL 실행 중인 요약이 없고, 마지막 요약 이후 바뀐 블록이 1개 이상이며, 다음 조건 중 하나를 만족할 때만 참을 돌려준다: (가) 요약이 아직 없고 바뀐 블록이 3개 이상, (나) 마지막 요약 후 90초 이상 지났고 바뀐 블록이 3개 이상, (다) 마지막 요약 후 10분 이상 지남.
7. WHERE 1단계 이후 구성이면, WHEN `SUMMARY` 작업이 실행되면, THE Pipeline SHALL 이전 요약과 마지막 요약 이후 바뀐 블록만 프롬프트에 넣는다.

### Requirement 17: 작업 큐와 워커

**User Story:** As a 개발자, I want 오래 걸리는 처리가 DB 기반 큐에서 재시도와 함께 돌기를, so that 추가 서비스 없이 실패와 프로세스 중단을 견딘다.

**단계:** 0단계

#### Acceptance Criteria

1. WHEN 작업 등록이 요청되면, THE Job_Queue SHALL 대상 세션이 요청한 `owner_id` 소유인지 확인한 뒤 `status=queued`, `attempts=0`인 작업을 만든다.
2. WHEN Worker가 다음 작업을 요청하면, THE Job_Queue SHALL `status=queued`이고 `run_after`가 현재 시각 이전인 작업 중 가장 오래된 작업 하나를 원자적으로 `running`으로 바꿔 돌려준다.
3. IF 작업 실행이 실패하고 시도 횟수가 3회 미만이면, THEN THE Job_Queue SHALL 지수 백오프로 `run_after`를 늦추고 작업을 `queued`로 되돌린다.
4. IF 작업 실행이 3회 실패하면, THEN THE Job_Queue SHALL 작업을 `failed`로 남긴다.
5. WHEN 작업이 `failed`가 되면, THE Worker SHALL SSE로 `job.failed` 이벤트를 보낸다.
6. IF 작업이 `running` 상태로 15분 넘게 머물면, THEN THE Job_Queue SHALL 해당 작업을 `queued`로 되돌린다.
7. THE Job_Queue SHALL `last_error`에 시크릿 값, 프롬프트 원문, 전사 원문을 넣지 않고 오류 종류와 요약만 기록한다.

### Requirement 18: 출처 대응표와 사실 추출

**User Story:** As a 행사 참석자, I want AI가 뽑은 사실마다 실제 메모, 사진, 쪽, 전사 구간이 연결되기를, so that 초안의 모든 내용을 원문으로 확인할 수 있다.

**단계:** 0단계

#### Acceptance Criteria

1. WHEN 초안 생성이 시작되면, THE Pipeline SHALL 세션의 비어 있지 않은 Memo_Block, 유효한 동의가 있는 전사 구간, 설명이 있는 사진, 발표자료와 참고자료의 Doc_Chunk를 라벨(`S1`, `S2`, ...)이 붙은 Source_Map으로 만든다.
2. THE Pipeline SHALL Source_Map의 라벨을 겹치지 않게 붙이고, 모든 Source_Ref의 대상을 같은 세션의 객체로 한정한다.
3. THE Pipeline SHALL 메모 블록 Source_Ref에 출처 수집 당시의 `revision`을 기록한다.
4. THE Pipeline SHALL Source_Ref마다 사람이 읽는 위치(메모 블록 순번, 전사 타임스탬프, 사진 파일 이름, 자료 이름과 쪽 번호)를 `locator`로 기록한다.
5. THE Pipeline SHALL 프롬프트에 출처 라벨과 출처 텍스트만 넣고, 실제 대상 ID는 서버의 Source_Map에만 둔다.
6. THE Pipeline SHALL 프롬프트에서 출처 텍스트를 `<source id="...">` 구분자로 감싸고, 구분자 안의 지시를 따르지 말라는 문구를 넣는다.
7. WHEN 출처 텍스트 합이 24,000자를 넘으면, THE Fact_Extractor SHALL 출처를 라벨 순서대로 24,000자 이하 묶음으로 나눠 LLM을 묶음마다 부르고 결과를 합친다.
8. THE Fact_Extractor SHALL 저장하는 모든 Fact에 Source_Ref를 하나 이상 붙인다.
9. IF LLM이 돌려준 사실에 출처 라벨이 없거나 해당 묶음의 Source_Map에 없는 라벨이 있으면, THEN THE Fact_Extractor SHALL 그 사실을 버리고 버린 개수를 지표 `facts.dropped_unknown_label`로 기록한다.
10. WHEN 정규화한 텍스트와 출처 라벨 집합이 같은 사실이 둘 이상 나오면, THE Fact_Extractor SHALL 그중 하나만 남긴다.

### Requirement 19: 템플릿에 따른 초안 작성

**User Story:** As a 행사 참석자, I want 고른 템플릿 형식으로 초안이 만들어지기를, so that 블로그나 링크드인 글을 처음부터 쓰지 않아도 된다.

**단계:** 0단계

#### Acceptance Criteria

1. WHEN Owner가 템플릿을 골라 초안 만들기를 요청하면, THE Job_Queue SHALL 세션 ID와 템플릿 ID를 담은 `DRAFT` 작업을 등록한다.
2. WHEN `DRAFT` 작업이 실행되면, THE Pipeline SHALL `collect_sources`, `extract_facts`, `compose_draft`, `verify_draft`를 이 순서로 실행한다.
3. THE Draft_Composer SHALL 프롬프트에 출처 원문 대신 사실 목록(`F1`, `F2`, ... 라벨)과 템플릿 섹션을 넣는다.
4. THE Draft_Composer SHALL 모든 AI 문장을 `origin=ai`, `verify_status=unverified`로 만들고, 문장이 인용한 사실 라벨을 Fact ID로 바꿔 저장한다.
5. IF LLM 응답에 템플릿에 없는 섹션 ID가 있으면, THEN THE Draft_Composer SHALL 해당 섹션을 버린다.
6. WHEN 한 섹션의 문장 수가 섹션의 `max_sentences`를 넘으면, THE Draft_Composer SHALL 앞에서부터 `max_sentences`개만 남긴다.
7. IF 문장이 인용한 사실 라벨이 사실 목록에 없으면, THEN THE Draft_Composer SHALL 해당 라벨을 문장의 `fact_ids`에서 뺀다.
8. WHEN 초안이 만들어지면, THE Pipeline SHALL 생성 당시의 템플릿을 `template_snapshot`으로 Draft에 저장하고, 전사 구간을 출처로 썼으면 `uses_recording`을 참으로 기록한다.
9. WHEN `verify_draft`가 끝나면, THE Pipeline SHALL Draft 상태를 `in_review`로 저장하고 그래프를 끝낸다.
10. WHEN Draft가 `in_review`로 저장되면, THE Worker SHALL SSE로 `draft.ready` 이벤트를 보낸다.
11. IF 초안 생성 중 `LLMError`가 나면, THEN THE Pipeline SHALL Draft 상태를 `failed`로 저장하고 문장을 남기지 않는다.

### Requirement 20: 사실 검증과 미검증 표시

**User Story:** As a 행사 참석자, I want 출처로 확인되지 않은 AI 문장이 "미검증"으로 표시되기를, so that 지어낸 내용이 검토 없이 나가지 않는다.

**단계:** 0단계

#### Acceptance Criteria

1. WHEN 검증이 실행되면, THE Verifier SHALL `origin`이 `ai`인 모든 문장의 검증 상태를 `verified` 또는 `unverified` 중 하나로 정한다.
2. IF 문장의 `fact_ids`가 비어 있거나 초안에 없는 Fact ID를 가리키면, THEN THE Verifier SHALL 문장을 Unverified_Sentence로 두고 "근거 사실 없음"을 기록한다.
3. IF 문장이 인용한 Fact의 출처가 삭제되었거나 메모 블록 `revision`이 출처 수집 당시와 다르면, THEN THE Verifier SHALL 문장을 Unverified_Sentence로 두고 "출처가 바뀌었거나 삭제됨"을 기록한다.
4. WHEN 구조 검사를 통과한 문장이 있으면, THE Verifier SHALL 해당 문장, 인용한 Fact, 그 Fact가 인용한 출처 원문만 LLM에 보내 지지 판정을 받는다.
5. THE Verifier SHALL 구조 검사와 지지 판정(`supported=true`)을 모두 통과한 문장만 `verified`로 정한다.
6. IF 지지 판정이 시간 초과, 응답 형식 오류, 응답 누락으로 끝나면, THEN THE Verifier SHALL 해당 문장을 Unverified_Sentence로 둔다.
7. THE Verifier SHALL `origin=user_insight`인 문장의 텍스트와 검증 상태를 그대로 둔다.
8. WHEN Owner가 "다시 검증"을 누르면, THE Verifier SHALL 현재 초안의 `ai`와 `ai_edited` 문장에 같은 검증을 다시 실행한다.
9. THE Web_UI SHALL Unverified_Sentence에 "미검증" 표시, kiro 보라 테두리, 처리 버튼을 붙인다.
10. THE Web_UI SHALL 문장마다 출처 칩을 보여 주고, Owner가 칩을 누르면 해당 메모 블록, 사진, 자료 쪽, 전사 구간으로 이동한다.

### Requirement 21: 템플릿 고르기, 저장, 재사용

**User Story:** As a 행사 참석자, I want 내장 템플릿을 고르고 내 형식으로 고쳐 저장하기를, so that 다음 행사에서도 같은 형식을 다시 쓸 수 있다.

**단계:** 내장 템플릿과 목록은 0단계, 복제와 수정은 1단계, 대학 과제와 출장 보고서 템플릿은 2단계

#### Acceptance Criteria

1. THE Template_Service SHALL 내장 블로그 템플릿과 내장 링크드인 템플릿을 `templates_builtin/*.toml` 파일로 제공한다. `[가정 A6]`
2. WHEN Owner가 템플릿 목록을 요청하면, THE Template_Service SHALL 내장 템플릿과 Owner의 템플릿을 함께 돌려준다.
3. WHERE 1단계 이후 구성이면, WHEN Owner가 템플릿 복제를 요청하면, THE Template_Service SHALL 새 ID와 Owner의 `owner_id`를 가진 사본을 만든다.
4. WHERE 1단계 이후 구성이면, WHEN Owner가 자기 템플릿을 저장하면, THE Template_Service SHALL 변경을 저장하고 다음 초안 만들기의 템플릿 목록에 넣는다.
5. IF 내장 템플릿(`owner_id`가 없음) 수정 요청이 오면, THEN THE Template_Service SHALL 수정을 거부한다.
6. IF 템플릿 섹션 수가 1~20개를 벗어나거나, 섹션 작성 지시가 1~2,000자를 벗어나거나, 섹션 `max_sentences`가 1~30을 벗어나면, THEN THE Template_Service SHALL 저장을 거부하고 검증 오류를 돌려준다.
7. WHEN 앱이 내장 템플릿 TOML 파일을 읽으면, THE Template_Parser SHALL 파일을 Template 객체로 바꾼다.
8. IF 내장 템플릿 TOML 파일이 스키마를 지키지 않으면, THEN THE Template_Parser SHALL 파일 이름과 이유를 담은 오류를 낸다.
9. THE Template_Serializer SHALL Template 객체를 `template_snapshot`용 JSON 문자열로 쓴다.
10. THE Template_Parser SHALL 모든 유효한 Template 객체에 대해 Template_Serializer가 쓴 JSON을 읽어 원래 객체와 같은 Template 객체를 만든다 (왕복 속성).
11. WHEN 초안을 만든 뒤 원래 템플릿이 수정되면, THE Review_Service SHALL 해당 초안을 `template_snapshot` 기준으로 보여 준다.

### Requirement 22: 인사이트 추가와 문장 검토

**User Story:** As a 행사 참석자, I want 초안에 내 생각을 더하고 미검증 문장을 직접 처리하기를, so that 결과물이 내 관점을 담고 사실과 맞게 된다.

**단계:** 0단계 (수정 문장 재검증은 1단계)

#### Acceptance Criteria

1. WHEN Owner가 섹션에 인사이트를 추가하면, THE Review_Service SHALL 지정한 위치에 `origin=user_insight`, `verify_status=n/a`인 문장을 만든다.
2. WHEN Owner가 AI 문장을 수정하면, THE Review_Service SHALL 문장 텍스트를 바꾸고 `origin`을 `ai_edited`로 바꾼다.
3. WHERE 0단계 구성이면, WHEN Owner가 AI 문장을 수정하면, THE Review_Service SHALL 기존 출처 연결을 유지하고 "사용자가 수정함" 표시를 붙인다.
4. WHERE 1단계 이후 구성이면, WHEN Owner가 AI 문장을 수정하면, THE Verifier SHALL 수정한 문장이 인용한 출처와 맞는지 다시 판정한다.
5. WHEN Owner가 Unverified_Sentence에 `keep_as_opinion`을 고르면, THE Review_Service SHALL 문장의 검증 상태를 `kept_as_opinion`으로 바꾼다.
6. WHEN Owner가 Unverified_Sentence에 `delete`를 고르면, THE Review_Service SHALL 해당 문장을 초안에서 지운다.
7. WHEN Owner가 Unverified_Sentence에 `attach_source`로 같은 세션의 출처를 고르면, THE Review_Service SHALL 고른 출처를 문장의 근거로 연결하고 문장의 검증 상태를 다시 판정한다.
8. IF `attach_source`로 고른 출처가 다른 세션의 대상이면, THEN THE Review_Service SHALL 연결을 거부한다.
9. THE Web_UI SHALL 승인 버튼에 남은 Unverified_Sentence 수를 보여 준다.
10. THE Web_UI SHALL 다른 사람의 이름과 연락처가 섞인 메모를 검토 화면에 원문 그대로 보여 주고, 지울지 여부를 Owner가 정하게 한다.

### Requirement 23: 사람만 하는 승인

**User Story:** As a 행사 참석자, I want 내가 승인한 초안만 완성본이 되기를, so that 에이전트가 검토 없이 결과물을 확정하지 않는다.

**단계:** 0단계

#### Acceptance Criteria

1. WHEN Owner가 `in_review` 상태 초안의 승인을 요청하고 Unverified_Sentence가 없으면, THE Review_Service SHALL 초안 상태를 `approved`로 바꾸고 `approved_at`을 기록한다.
2. IF 승인 요청 시점에 Unverified_Sentence가 하나라도 남아 있으면, THEN THE Review_Service SHALL 409와 남은 문장 ID 목록을 돌려주고 초안 상태를 그대로 둔다.
3. IF 초안의 `uses_recording`이 참이고 해당 녹음의 Consent_Record가 철회되었으면, THEN THE Review_Service SHALL 승인을 거부한다.
4. IF 초안 상태가 `in_review`가 아니면, THEN THE Review_Service SHALL 승인을 거부한다.
5. THE Review_Service SHALL 로그인한 Owner의 승인 HTTP 요청을 받았을 때만 초안 상태를 `approved`로 바꾼다.
6. THE Pipeline SHALL 초안 상태를 `in_review`, `failed`, `generating` 중 하나로만 바꾼다.

### Requirement 24: 승인된 초안 내보내기

**User Story:** As a 행사 참석자, I want 승인한 초안을 AI 생성 표시와 출처 목록이 붙은 마크다운으로 받기를, so that 내가 직접 블로그나 링크드인에 올릴 수 있다.

**단계:** 마크다운과 클립보드는 0단계 `[가정 A8]`, HTML은 1단계, DOCX와 PDF는 2단계

#### Acceptance Criteria

1. WHEN Owner가 `approved` 초안의 마크다운 내보내기를 요청하면, THE Exporter SHALL 마크다운 파일 응답을 돌려준다.
2. IF 내보내기 대상 초안의 상태가 `approved`가 아니면, THEN THE Exporter SHALL 409를 돌려주고 결과물을 만들지 않는다.
3. THE Exporter SHALL 모든 내보내기 결과의 맨 위에 AI 생성 표시 문구를 넣는다.
4. THE Exporter SHALL `kept_as_opinion` 문장 뒤에 "(출처 미확인)" 표시를 붙인다.
5. THE Exporter SHALL 결과 맨 아래 출처 목록에 결과에 들어간 문장이 인용한 Fact의 출처만 넣는다.
6. THE Exporter SHALL 녹음 출처를 전사 텍스트 없이 타임스탬프로만 적는다.
7. THE Exporter SHALL 결과를 HTTP 파일 응답 또는 클립보드용 텍스트로만 돌려주고, 외부 서비스에 게시하거나 전송하는 기능을 두지 않는다.
8. THE Web_UI SHALL 내보내기 화면에 마크다운 미리보기, 파일 내려받기, 클립보드 복사 버튼을 제공한다.
9. WHERE 1단계 이후 구성이면, THE Exporter SHALL 같은 규칙으로 HTML 형식 내보내기를 제공한다.

### Requirement 25: 인증과 소유자 격리

**User Story:** As a 소유자, I want 내 기록에 나만 접근하기를, so that 행사 기록과 녹음이 다른 사람에게 노출되지 않는다.

**단계:** 0단계 (여러 사용자는 2단계) `[가정 A1]`

#### Acceptance Criteria

1. THE Auth SHALL Owner 1명을 `OWNER_PASSWORD_HASH` 환경 변수의 argon2 해시로 인증한다.
2. WHEN 로그인이 성공하면, THE Auth SHALL `SESSION_SECRET`으로 서명한 `HttpOnly`, `Secure`, `SameSite=Lax` 세션 쿠키를 발급한다.
3. IF 한 IP 주소에서 1분 안에 로그인 시도가 5회를 넘으면, THEN THE Auth SHALL 해당 1분 동안 추가 로그인 시도를 거부한다.
4. IF 로그인하지 않은 요청이 `/login`과 `/healthz` 밖의 경로로 오면, THEN THE Auth SHALL 요청을 거부한다.
5. IF 상태를 바꾸는 요청에 유효한 CSRF 토큰(폼 토큰 또는 `X-CSRF-Token` 헤더)이 없으면, THEN THE Auth SHALL 요청을 거부한다.
6. THE Web_UI SHALL 모든 HTMX 요청에 `X-CSRF-Token` 헤더를 자동으로 붙인다.
7. THE Open_Attendee SHALL 모든 데이터를 `owner_id`로 소유자와 묶고, 모든 API 응답에 요청한 Owner 소유의 객체만 넣는다.

### Requirement 26: 설정, 시크릿, 상태 검사

**User Story:** As a 운영자, I want 시크릿을 환경 변수로만 넣고 상태를 안전하게 확인하기를, so that 키가 코드나 로그에 새지 않는다.

**단계:** 0단계 (`doctor` 명령은 1단계)

#### Acceptance Criteria

1. THE Open_Attendee SHALL API 키, 비밀번호 해시, 쿠키 서명 키를 환경 변수(Kubernetes에서는 Secret을 `envFrom`으로 넣은 환경 변수)로만 받는다.
2. IF `OWNER_PASSWORD_HASH` 또는 `SESSION_SECRET`이 설정되지 않았으면, THEN THE Open_Attendee SHALL 시작을 거부하고 빠진 변수 이름을 알린다.
3. THE Open_Attendee SHALL 로그와 오류 메시지에 시크릿 값, 프롬프트 원문, 전사 원문을 넣지 않는다.
4. WHEN `/healthz` 요청이 오면, THE Open_Attendee SHALL 준비 상태, LLM 설정 여부, 현재 LLM 제공자와 리전, 저장소 남은 용량을 돌려주고 시크릿 값은 넣지 않는다.
5. THE Web_UI SHALL 설정 화면에 현재 LLM 제공자와 리전을 보여 준다.
6. THE Open_Attendee SHALL `.env` 파일을 저장소에 커밋하지 않도록 `.gitignore`에 두고, 설정 예시는 `.env.example`로만 제공한다.
7. WHERE 1단계 이후 구성이면, WHEN Owner가 `doctor` 명령을 실행하면, THE Open_Attendee SHALL LLM 호출 1회, Blob_Store 쓰기와 삭제, ffmpeg 존재 여부를 확인해 결과를 출력한다.

### Requirement 27: 배포

**User Story:** As a 운영자, I want 같은 이미지를 맥북, 온프레미스 Kubernetes, AWS에 배포하기를, so that 환경마다 다른 빌드를 관리하지 않는다.

**단계:** 맥북과 온프레미스는 0단계, AWS S3는 1단계, AWS GPU 전사는 2단계

#### Acceptance Criteria

1. THE Deployment_Package SHALL 같은 컨테이너 이미지를 `linux/amd64`와 `linux/arm64`로 빌드한다.
2. THE Deployment_Package SHALL 컨테이너를 비루트 사용자로 실행하고 8080 포트로 서비스한다.
3. THE Deployment_Package SHALL helm 차트에 데이터용 PVC, Secret을 넣는 `envFrom`, `/healthz` 준비 상태 검사, 메모리 한도 512Mi를 둔다.
4. THE Deployment_Package SHALL helm 차트의 `replicaCount`를 1로 고정하고 `allowPrivilegeEscalation: false`를 유지한다.
5. THE Deployment_Package SHALL `faster-whisper`를 선택 의존성(`stt`)으로 두고, `linux/arm64` 이미지에는 넣지 않는다.
6. WHERE 배포 대상이 Raspberry Pi 온프레미스 클러스터이면, THE Deployment_Package SHALL `TRANSCRIBER`를 `none` 또는 `remote`로 설정한다. `[가정 A3]`
7. WHERE 배포 대상이 맥북이면, THE Open_Attendee SHALL `uv run` 명령과 `docker run` 명령 두 방식으로 시작할 수 있다.
8. WHERE Bedrock 제공자를 쓰면, THE LLM_Gateway SHALL `AWS_REGION` 값(기본 `us-east-1`)의 Bedrock 엔드포인트를 부른다. `[가정 A2]`
9. THE Open_Attendee SHALL SQLite를 WAL 모드와 `busy_timeout` 설정으로 연다.
10. THE Open_Attendee SHALL 앱 코드를 이 저장소의 `webapp/` 디렉터리에 둔다. `[가정 A9]`

### Requirement 28: 효과 측정

**User Story:** As a 제품 담당자, I want 정리 시간과 초안 품질을 기록하기를, so that "정리 시간 30분 이내" 목표를 실제로 확인할 수 있다.

**단계:** 1단계 (목표 수치는 측정 전 가정)

#### Acceptance Criteria

1. WHERE 1단계 이후 구성이면, WHEN 초안이 승인되면, THE Review_Service SHALL 세션의 마지막 기록 시각부터 승인 시각까지 걸린 시간을 기록한다.
2. WHERE 1단계 이후 구성이면, WHEN 초안이 승인되면, THE Review_Service SHALL AI 문장 중 `verified` 비율과 Owner가 지운 AI 문장 비율을 기록한다.
3. WHERE 1단계 이후 구성이면, WHEN 초안 생성이 끝나면, THE LLM_Gateway SHALL 해당 초안의 LLM 호출 수와 입력, 출력 글자 수 합계를 기록한다.
