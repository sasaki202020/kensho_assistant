"use strict";

const status = document.getElementById("status");

document.getElementById("clear").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "CLEAR_SESSION_PROFILE" }, (response) => {
    status.textContent = response?.ok ? "セッション情報を消去しました" : "消去できませんでした";
  });
});

document.getElementById("reload-extension").addEventListener("click", () => {
  status.textContent = "拡張機能を更新しています";
  setTimeout(() => chrome.runtime.reload(), 100);
});
