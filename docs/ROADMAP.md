# 로드맵

## 지원 범위 (지금)

- 설치 환경: **웹앱**만 지원해요.
- 작업 공간: 사이드바에서 내 행사와 필기·자료·AI 요약·초안으로 이동해요. 작은 화면에서는 메뉴를 접을 수 있어요. [#35](https://github.com/jyje/open-attendee/issues/35)
- 자료 업로드: 키보드로 사진·발표자료·참고자료의 파일 선택을 열 수 있어요. [#36](https://github.com/jyje/open-attendee/issues/36)
- 승인한 초안에서 마지막 필기 수정이나 자료 추가부터 승인까지의 경과 시간을 확인할 수 있어요. [#61](https://github.com/jyje/open-attendee/issues/61)
- 요약 출처에는 자료 종류와 위치를 한 번씩 표시해요. [#49](https://github.com/jyje/open-attendee/issues/49)
- 자료 화면에서 발표자료와 참고자료를 원래 파일 이름으로 내려받을 수 있어요. [#54](https://github.com/jyje/open-attendee/issues/54)
- 첨부 파일은 로컬 볼륨이나 S3에 저장할 수 있어요. [#53](https://github.com/jyje/open-attendee/issues/53)
- 배포 대상: **온프레미스 Kubernetes 클러스터**.
- 상태 점검 명령에서 준비 상태, LLM 설정, 첨부 저장소를 조회할 수 있어요. [#57](https://github.com/jyje/open-attendee/issues/57)
- 환경별 Helm 값 파일에서 개발·스테이징·운영 이미지를 선택해요. [#59](https://github.com/jyje/open-attendee/issues/59)
- 배포 방식: **k8s + Helm 네이티브**. 차트는 `helm/`, 이미지는 `docker/`에 있어요.
- CI와 이미지 빌드의 GitHub Actions는 Node.js 24 런타임을 사용해요. [#44](https://github.com/jyje/open-attendee/issues/44)

## 예정

| 항목 | 상태 | 비고 |
|---|---|---|
| 행사 정리 시간 비교 | 예정 | 같은 자료와 결과물 기준으로 수작업과 앱 사용 시간을 비교해요. [#62](https://github.com/jyje/open-attendee/issues/62) |
| macOS (맥북) 지원 | 예정 | 지금은 웹앱만 제공해요. |
| iOS 지원 | 예정 | 지금은 웹앱만 제공해요. |
| AWS EKS 레시피 | 예정 | 같은 Helm 차트를 EKS에 올리는 방법을 정리해요. |
| AWS ECS 레시피 | 예정 | Helm을 쓰지 않으니 작업 정의(task definition)를 새로 만들어요. |

## 지금 하지 않는 것

- 맥북, iOS 앱 빌드와 배포.
- EKS, ECS 배포 파일.
