// 모든 HTMX 요청에 X-CSRF-Token 헤더를 자동으로 붙인다(요구사항 25.6).
// 토큰은 base.html의 <meta name="csrf-token">에서 읽는다.
(function () {
  "use strict";

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") || "" : "";
  }

  // fetch를 직접 쓰는 스크립트(예: 녹음 업로드)도 같은 토큰을 쓸 수 있게 노출한다.
  window.oaCsrfToken = csrfToken;

  document.addEventListener("htmx:configRequest", function (event) {
    var token = csrfToken();
    if (token) {
      event.detail.headers["X-CSRF-Token"] = token;
    }
  });
})();
