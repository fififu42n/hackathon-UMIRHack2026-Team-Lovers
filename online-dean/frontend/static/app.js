// Онлайн-деканат: подключение страницы к серверу (/api/analyze, /api/answer)
(() => {
  const $ = (id) => document.getElementById(id);
  const fileInput = $("file-input"), docType = $("doc-type"), questionEl = $("question");
  const checkBtn = $("check-btn"), errorBox = $("error-box"), errorText = $("error-text");
  const state = { card: null };            // последняя распознанная карточка (чтобы не гонять OCR повторно)

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function showError(msg, hint) {
    errorText.textContent = msg + (hint ? " " + hint : "");
    errorBox.hidden = false;
    $("results").hidden = true;
  }
  const hideError = () => { errorBox.hidden = true; };

  function reset() { state.card = null; }
  fileInput.addEventListener("change", () => {
    reset(); hideError();
    $("file-name").textContent = fileInput.files[0] ? fileInput.files[0].name : "Перетащите документ сюда";
  });
  docType.addEventListener("change", reset);
  $("retry-btn").addEventListener("click", () => { fileInput.value = ""; reset(); hideError(); $("file-name").textContent = "Перетащите документ сюда"; fileInput.click(); });

  function render(r) {
    const missing = r.validation.status === "missing_fields";
    $("res-title").textContent = r.document_title || "Результат проверки";
    const pill = $("res-status");
    pill.textContent = missing ? "Не хватает сведений" : "Все сведения на месте";
    pill.className = "status-pill " + (missing ? "missing" : "ok");
    $("res-fields").innerHTML = r.card.map((f) =>
      `<tr class="${f.status}"><td>${esc(f.label)}</td><td>${esc(f.value)}</td></tr>`).join("");
    $("res-q-title").textContent = r.asked_question ? "Ответ на ваш вопрос" : "Предварительная проверка";
    $("res-answer").textContent = r.answer.answer;
    $("res-rules").innerHTML = r.cited_rules.map((c) =>
      `<div class="rule"><b>Положение, п. ${esc(c.id)}</b>${esc(c.text)}</div>`).join("");
    if (r.ocr_text !== undefined) { $("res-ocr").textContent = r.ocr_text; $("res-ocr-wrap").hidden = false; }
    $("results").hidden = false;
    $("results").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function post(url, body, isForm) {
    const resp = await fetch(url, { method: "POST", body: isForm ? body : JSON.stringify(body),
      headers: isForm ? {} : { "Content-Type": "application/json" } });
    const data = await resp.json().catch(() => ({ error: "Сервер вернул не JSON" }));
    if (!resp.ok) throw Object.assign(new Error(data.error || "Ошибка " + resp.status), { hint: data.hint });
    return data;
  }

  checkBtn.addEventListener("click", async () => {
    hideError();
    const question = questionEl.value.trim();
    checkBtn.disabled = true;
    const label = checkBtn.lastChild, labelText = label.textContent;
    label.textContent = " Обработка, подождите… ";
    try {
      let result;
      if (state.card && question) {                        // повторный вопрос по тому же файлу: без OCR
        result = await post("/api/answer", { ...state.card, question }, false);
      } else {
        const file = fileInput.files[0];
        if (!file) throw new Error("Сначала загрузите документ");
        const fd = new FormData();
        fd.append("file", file); fd.append("document_type", docType.value); fd.append("question", question);
        result = await post("/api/analyze", fd, true);
        $("res-ocr-wrap").hidden = result.ocr_text === undefined;
      }
      state.card = { document_id: result.document_id, document_type: result.document_type, fields: result.fields };
      render(result);
    } catch (e) {
      showError(e.message, e.hint);
    } finally {
      label.textContent = labelText;
      checkBtn.disabled = false;
    }
  });
})();
