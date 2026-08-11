(() => {
  "use strict";

  const GENERIC_ERROR_MESSAGE = "요청을 처리하지 못했습니다.";
  const DISPLAYABLE_ERROR_CODES = new Set([
    "validation_error",
    "db_save_error",
    "internal_error",
    "openai_api_error",
    "openai_timeout",
  ]);
  const ISO_TIMESTAMP_PATTERN =
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

  const form = document.getElementById("chat-form");
  const messageInput = document.getElementById("chat-message");
  const submitButton = document.getElementById("chat-submit");
  const formError = document.getElementById("chat-form-error");
  const history = document.getElementById("chat-history");
  const pendingTemplate = document.getElementById("chat-pending-template");

  if (
    !form ||
    !messageInput ||
    !submitButton ||
    !formError ||
    !history ||
    !pendingTemplate
  ) {
    return;
  }

  let isSubmitting = false;

  function isObject(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
  }

  function parseSuccessPayload(payload) {
    if (
      !isObject(payload) ||
      !Number.isInteger(payload.chat_exchange_id) ||
      payload.chat_exchange_id <= 0 ||
      typeof payload.answer !== "string" ||
      typeof payload.created_at !== "string" ||
      !ISO_TIMESTAMP_PATTERN.test(payload.created_at)
    ) {
      return null;
    }

    const createdAt = new Date(payload.created_at);
    if (Number.isNaN(createdAt.getTime())) {
      return null;
    }

    return {
      chatExchangeId: payload.chat_exchange_id,
      answer: payload.answer,
      createdAt: payload.created_at,
      createdAtText: `${createdAt.toISOString().slice(0, 19).replace("T", " ")} UTC`,
    };
  }

  function parseErrorPayload(payload) {
    if (
      !isObject(payload) ||
      typeof payload.code !== "string" ||
      typeof payload.detail !== "string"
    ) {
      return null;
    }

    return { code: payload.code, detail: payload.detail };
  }

  function setFormError(message = "") {
    formError.textContent = message;
    formError.hidden = message.length === 0;
  }

  function createPendingExchange(question) {
    const exchange = pendingTemplate.content.firstElementChild.cloneNode(true);
    const questionElement = exchange.querySelector("[data-chat-question]");
    const responseElement = exchange.querySelector("[data-chat-response]");
    const timeElement = exchange.querySelector("[data-chat-time]");

    questionElement.textContent = question;
    document.getElementById("chat-empty-state")?.remove();
    history.append(exchange);

    return { exchange, responseElement, timeElement };
  }

  function renderSuccess(pendingExchange, result) {
    pendingExchange.exchange.classList.remove("chat-exchange--pending");
    pendingExchange.exchange.setAttribute(
      "data-chat-exchange-id",
      String(result.chatExchangeId),
    );
    pendingExchange.responseElement.textContent = result.answer;
    pendingExchange.timeElement.setAttribute("datetime", result.createdAt);
    pendingExchange.timeElement.textContent = result.createdAtText;
    pendingExchange.timeElement.hidden = false;
  }

  function renderFailure(pendingExchange, message) {
    pendingExchange.exchange.classList.remove("chat-exchange--pending");
    pendingExchange.exchange.classList.add("chat-exchange--failed");
    pendingExchange.responseElement.removeAttribute("aria-live");
    pendingExchange.responseElement.setAttribute("role", "alert");
    pendingExchange.responseElement.textContent = message;
  }

  function restoreIdleState() {
    isSubmitting = false;
    submitButton.disabled = false;
    messageInput.focus();
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

    const submittedQuestion = messageInput.value.trim();
    if (submittedQuestion.length === 0) {
      setFormError("질문을 입력해주세요.");
      return;
    }
    if (submittedQuestion.length > 1000) {
      setFormError("질문은 1000자 이하로 입력해주세요.");
      return;
    }

    setFormError();
    messageInput.value = "";
    isSubmitting = true;
    submitButton.disabled = true;

    const pendingExchange = createPendingExchange(submittedQuestion);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify({ message: submittedQuestion }),
      });
      const payload = await response.json();

      if (response.ok) {
        const result = parseSuccessPayload(payload);
        if (result === null) {
          renderFailure(pendingExchange, GENERIC_ERROR_MESSAGE);
        } else {
          renderSuccess(pendingExchange, result);
        }
      } else {
        const error = parseErrorPayload(payload);
        if (error?.code === "not_authenticated") {
          window.location.assign("/login");
          return;
        }

        const message =
          error !== null && DISPLAYABLE_ERROR_CODES.has(error.code)
            ? error.detail
            : GENERIC_ERROR_MESSAGE;
        renderFailure(pendingExchange, message);
      }
    } catch {
      renderFailure(pendingExchange, GENERIC_ERROR_MESSAGE);
    }

    restoreIdleState();
  });
})();
