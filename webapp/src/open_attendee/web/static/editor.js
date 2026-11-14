// 기록 화면: 메모 블록 편집기와 모바일 탭.
// 블록 ID는 브라우저가 UUID로 만들고, 서버는 그 ID로 저장한다(요구사항 2.1).
(function () {
  "use strict";

  var record = document.getElementById("record");
  var blocks = document.getElementById("blocks");
  var composer = document.getElementById("composer");
  var composerText = document.getElementById("composer-text");
  var template = document.getElementById("block-template");
  if (!record || !blocks) {
    return;
  }

  function newUuid() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    // randomUUID가 없는 오래된 브라우저(또는 http 주소)를 위한 대체. 버전 4 형식.
    var bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    var hex = Array.prototype.map
      .call(bytes, function (b) {
        return ("0" + b.toString(16)).slice(-2);
      })
      .join("");
    return [
      hex.slice(0, 8),
      hex.slice(8, 12),
      hex.slice(12, 16),
      hex.slice(16, 20),
      hex.slice(20),
    ].join("-");
  }

  function addBlock(text) {
    var holder = document.createElement("div");
    holder.innerHTML = template.innerHTML.split("__ID__").join(newUuid());
    var form = holder.firstElementChild;
    form.querySelector("textarea").value = text;
    blocks.appendChild(form);
    window.htmx.process(form);
    // 입력을 기다리지 않고 바로 첫 저장을 보낸다.
    window.htmx.trigger(form, "save");
    return form;
  }

  if (composer && composerText && template) {
    composer.addEventListener("submit", function (event) {
      event.preventDefault();
      var text = composerText.value;
      if (!text.trim()) {
        composerText.focus();
        return;
      }
      addBlock(text);
      composerText.value = "";
      composerText.focus();
    });
    composerText.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        composer.requestSubmit();
      }
    });
  }

  // 마지막으로 저장한 글과 같으면 요청을 보내지 않는다(수정 번호가 쓸데없이 오르지 않게).
  function blockOf(event) {
    var target = event.target;
    return target && target.closest ? target.closest(".block") : null;
  }

  document.addEventListener("htmx:beforeRequest", function (event) {
    var form = blockOf(event);
    var config = event.detail && event.detail.requestConfig;
    if (!form || !config || String(config.verb).toLowerCase() !== "put") {
      return;
    }
    var value = form.querySelector("textarea").value;
    if (value === form.dataset.saved) {
      event.preventDefault();
      return;
    }
    form._pending = value;
  });

  document.addEventListener("htmx:afterRequest", function (event) {
    var form = blockOf(event);
    var config = event.detail && event.detail.requestConfig;
    if (!form || !config || String(config.verb).toLowerCase() !== "put") {
      return;
    }
    if (event.detail.successful && typeof form._pending === "string") {
      form.dataset.saved = form._pending;
    }
  });

  function showSaveFailure(event) {
    var form = blockOf(event);
    if (!form) {
      return;
    }
    var status = form.querySelector(".block__status");
    if (status) {
      status.textContent = "저장하지 못했어요. 잠시 뒤에 다시 시도해 주세요.";
    }
  }
  document.addEventListener("htmx:responseError", function (event) {
    // 요약 영역이 아직 없는 경우(404)는 오류로 보여 주지 않는다.
    if (event.detail.xhr && event.detail.xhr.status === 404 && !blockOf(event)) {
      return;
    }
    showSaveFailure(event);
  });
  document.addEventListener("htmx:sendError", showSaveFailure);

  // 모바일에서는 "기록"과 "요약"을 탭으로 나눠 보여 준다.
  var tabs = record.querySelectorAll("[data-tab-target]");
  Array.prototype.forEach.call(tabs, function (tab) {
    tab.addEventListener("click", function () {
      record.dataset.tab = tab.dataset.tabTarget;
      Array.prototype.forEach.call(tabs, function (other) {
        other.setAttribute("aria-selected", other === tab ? "true" : "false");
      });
    });
  });
})();
