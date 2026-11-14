# 참고 출처: Cloudscape Design System

이 폴더의 파일은 AWS가 만든 오픈소스 디자인 시스템 Cloudscape에서 가져왔어요.

## 출처

| 항목 | 값 |
|---|---|
| 프로젝트 | Cloudscape Design System |
| 공식 사이트 | [cloudscape.design](https://cloudscape.design/) |
| 소스 저장소 | [cloudscape-design/components](https://github.com/cloudscape-design/components) |
| 가져온 패키지 | [@cloudscape-design/design-tokens 3.0.117](https://www.npmjs.com/package/@cloudscape-design/design-tokens) |
| 가져온 파일 | `index-visual-refresh.json` (토큰 571개) |
| 라이선스 | Apache-2.0 (`LICENSE`) |
| 저작권 | Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. (`NOTICE`) |

## 파일

- `cloudscape-tokens.css`: 토큰을 CSS 변수로 바꾼 파일이에요. 라이트 값은 `:root`, 다크 값은 `[data-theme="dark"]`에 있어요. 토큰 원본을 그대로 옮기지 않고 값만 바꿨어요.
- `LICENSE`, `NOTICE`: 패키지에서 그대로 가져왔어요.

## 가져오지 않은 것

- React 컴포넌트 코드는 가져오지 않았어요. 이 프로젝트 스택이 정해지지 않았기 때문이에요. 필요하면 [components 저장소](https://github.com/cloudscape-design/components)를 보세요.

## 바꾼 점

- 토큰 원본 JSON에서 CSS 변수만 뽑았어요. 값은 바꾸지 않았어요.
- 컴팩트 모드 값(`compact`)은 넣지 않고 기본 모드(`comfortable`) 값만 넣었어요.

## 라이선스 의무

Apache-2.0에 따라 이 파일을 쓰면 라이선스와 NOTICE를 함께 두어야 해요. 이 폴더에 두었어요.
