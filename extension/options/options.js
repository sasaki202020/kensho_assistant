"use strict";

const form = document.getElementById("profile-form");
const status = document.getElementById("status");

function profileFromForm() {
  const profile = {};
  for (const field of form.elements) {
    if (!field.name || typeof field.value !== "string") continue;
    if (field.value) profile[field.name] = field.value;
  }
  return profile;
}

function clearVisibleValues() {
  for (const field of form.elements) {
    if (field.name && typeof field.value === "string") field.value = "";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  chrome.runtime.sendMessage(
    { type: "SET_SESSION_PROFILE", profile: profileFromForm() },
    (response) => {
      if (!response?.ok) {
        status.textContent = "安全に読み込めませんでした";
        return;
      }
      clearVisibleValues();
      status.textContent = `${response.fieldCount}項目を一時セッションへ読み込みました`;
    }
  );
});

document.getElementById("clear").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "CLEAR_SESSION_PROFILE" }, (response) => {
    clearVisibleValues();
    status.textContent = response?.ok ? "セッション情報を消去しました" : "消去できませんでした";
  });
});

document.getElementById("reload-extension").addEventListener("click", () => {
  clearVisibleValues();
  status.textContent = "拡張機能を更新しています";
  setTimeout(() => chrome.runtime.reload(), 100);
});
