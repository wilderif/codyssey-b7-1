// Isolate the Chat page controller from the global browser scope.
(() => {
  "use strict";

  // Fallback text for responses that are unsafe or impossible to interpret.
  const GENERIC_ERROR_MESSAGE = "요청을 처리하지 못했습니다.";
  // Server error codes whose detail is safe to show to the user.
  const DISPLAYABLE_ERROR_CODES = new Set([
    "validation_error",
    "db_save_error",
    "internal_error",
    "openai_api_error",
    "openai_timeout",
  ]);
  // ISO 8601 shape accepted for a successful response timestamp.
  const ISO_TIMESTAMP_PATTERN =
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
  // Distance that keeps a reader anchored to the latest response update.
  const SCROLL_BOTTOM_THRESHOLD_PX = 48;
  // Shared input limit used by validation and the visible character counter.
  const MAX_MESSAGE_LENGTH = 1000;
  // Primary-pointer query that keeps virtual keyboards multiline-friendly.
  const COARSE_POINTER_QUERY = "(pointer: coarse)";
  // Keyboard guidance for devices with a precise primary pointer.
  const DESKTOP_INPUT_HELP = "Enter로 전송 · Shift+Enter로 줄바꿈";
  // Keyboard guidance for touch-first devices without a practical Shift key.
  const MOBILE_INPUT_HELP = "Enter로 줄바꿈 · 전송 버튼으로 보내기";

  // Form that owns the Chat submission flow.
  const form = document.getElementById("chat-form");
  // Text input that holds the user's draft question.
  const messageInput = document.getElementById("chat-message");
  // Button disabled while one request is in progress.
  const submitButton = document.getElementById("chat-submit");
  // Accessible container for client-side form errors.
  const formError = document.getElementById("chat-form-error");
  // Persistent keyboard guidance associated with the question control.
  const messageHelp = document.getElementById("chat-input-help");
  // Visible count associated with the question control without live announcements.
  const characterCount = document.getElementById("chat-character-count");
  // Timeline that receives pending and completed exchanges.
  const history = document.getElementById("chat-history");
  // Inert markup cloned for each pending exchange.
  const pendingTemplate = document.getElementById("chat-pending-template");

  // Leave unrelated pages untouched when any Chat dependency is absent.
  if (
    !form ||
    !messageInput ||
    !submitButton ||
    !formError ||
    !messageHelp ||
    !characterCount ||
    !history ||
    !pendingTemplate
  ) {
    return;
  }

  // Prevent duplicate requests until the active submission finishes.
  let isSubmitting = false;
  // Primary-pointer state used to separate Desktop and Mobile Enter behavior.
  const coarsePointer = window.matchMedia(COARSE_POINTER_QUERY);

  // Narrow an unknown JSON value to a plain object-like payload.
  function isObject(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
  }

  // Validate and normalize the success payload used by the renderer.
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

    // Parsed date used to reject impossible timestamps and build display text.
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

  // Validate the error payload before its code or detail is consumed.
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

  // Show one form error or hide the empty error container.
  function setFormError(message = "") {
    formError.textContent = message;
    formError.hidden = message.length === 0;
  }

  // Keep the concise keyboard guidance aligned with the active input mode.
  function updateInputHelp() {
    messageHelp.textContent = coarsePointer.matches
      ? MOBILE_INPUT_HELP
      : DESKTOP_INPUT_HELP;
  }

  // Reflect the raw textarea length without repeatedly announcing every keypress.
  function updateCharacterCount() {
    characterCount.value = `${messageInput.value.length} / ${MAX_MESSAGE_LENGTH}`;
  }

  // Submit with Desktop Enter while preserving multiline and IME composition.
  function handleMessageKeydown(event) {
    const isComposing = event.isComposing || event.keyCode === 229;
    if (
      event.key !== "Enter" ||
      event.shiftKey ||
      isComposing ||
      coarsePointer.matches
    ) {
      return;
    }

    event.preventDefault();
    form.requestSubmit(submitButton);
  }

  // Report whether the reader is still following the newest conversation.
  function isHistoryNearBottom() {
    const distanceFromBottom =
      history.scrollHeight - history.scrollTop - history.clientHeight;
    return distanceFromBottom <= SCROLL_BOTTOM_THRESHOLD_PX;
  }

  // Reveal the latest exchange inside the independently scrolling history.
  function scrollHistoryToLatest() {
    history.scrollTop = history.scrollHeight;
  }

  // Append a pending exchange and return the nodes updated after the request.
  function createPendingExchange(question) {
    // New exchange cloned from inert template markup.
    const exchange = pendingTemplate.content.firstElementChild.cloneNode(true);
    // Question node populated with user text through textContent.
    const questionElement = exchange.querySelector("[data-chat-question]");
    // Response node reserved for a success answer or safe error.
    const responseElement = exchange.querySelector("[data-chat-response]");
    // Timestamp node revealed only after a valid success response.
    const timeElement = exchange.querySelector("[data-chat-time]");

    questionElement.textContent = question;
    document.getElementById("chat-empty-state")?.remove();
    history.append(exchange);
    scrollHistoryToLatest();

    return { exchange, responseElement, timeElement };
  }

  // Replace a pending exchange with the validated server answer.
  function renderSuccess(pendingExchange, result) {
    const keepLatestVisible = isHistoryNearBottom();

    pendingExchange.exchange.classList.remove("chat-exchange--pending");
    pendingExchange.exchange.setAttribute(
      "data-chat-exchange-id",
      String(result.chatExchangeId),
    );
    pendingExchange.responseElement.textContent = result.answer;
    pendingExchange.timeElement.setAttribute("datetime", result.createdAt);
    pendingExchange.timeElement.textContent = result.createdAtText;
    pendingExchange.timeElement.hidden = false;

    if (keepLatestVisible) {
      scrollHistoryToLatest();
    }
  }

  // Mark a pending exchange as failed and announce its safe message.
  function renderFailure(pendingExchange, message) {
    const keepLatestVisible = isHistoryNearBottom();

    pendingExchange.exchange.classList.remove("chat-exchange--pending");
    pendingExchange.exchange.classList.add("chat-exchange--failed");
    pendingExchange.responseElement.removeAttribute("aria-live");
    pendingExchange.responseElement.setAttribute("role", "alert");
    pendingExchange.responseElement.textContent = message;

    if (keepLatestVisible) {
      scrollHistoryToLatest();
    }
  }

  // Re-enable input and restore focus after a completed request.
  function restoreIdleState() {
    isSubmitting = false;
    submitButton.disabled = false;
    messageInput.focus();
  }

  // Run the validation, request, rendering, and recovery phases in order.
  async function handleSubmit(event) {
    // Keep the browser from replacing the server-rendered page.
    event.preventDefault();

    // Ignore repeated submits while the current request is pending.
    if (isSubmitting) {
      return;
    }

    // Trimmed copy sent to the API and rendered in the timeline.
    const submittedQuestion = messageInput.value.trim();

    // Reject empty or oversized questions before changing the draft.
    if (submittedQuestion.length === 0) {
      setFormError("질문을 입력해주세요.");
      return;
    }
    if (submittedQuestion.length > MAX_MESSAGE_LENGTH) {
      setFormError("질문은 1000자 이하로 입력해주세요.");
      return;
    }

    // Clear the accepted draft and lock the form for one request.
    setFormError();
    messageInput.value = "";
    updateCharacterCount();
    isSubmitting = true;
    submitButton.disabled = true;

    // Optimistic exchange kept stable through success or failure rendering.
    const pendingExchange = createPendingExchange(submittedQuestion);

    // Send the accepted question and render only validated response data.
    try {
      // Same-origin API response for the active Chat Session.
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify({ message: submittedQuestion }),
      });
      // Unknown JSON payload validated before any fields are trusted.
      const payload = await response.json();

      if (response.ok) {
        // Normalized success result or null for a malformed payload.
        const result = parseSuccessPayload(payload);
        if (result === null) {
          renderFailure(pendingExchange, GENERIC_ERROR_MESSAGE);
        } else {
          renderSuccess(pendingExchange, result);
        }
      } else {
        // Validated API error or null for an unexpected error shape.
        const error = parseErrorPayload(payload);
        if (error?.code === "not_authenticated") {
          window.location.assign("/login");
          return;
        }

        // Whitelisted server detail or the generic safe fallback.
        const message =
          error !== null && DISPLAYABLE_ERROR_CODES.has(error.code)
            ? error.detail
            : GENERIC_ERROR_MESSAGE;
        renderFailure(pendingExchange, message);
      }
    } catch {
      renderFailure(pendingExchange, GENERIC_ERROR_MESSAGE);
    }

    // Restore the editable state after every non-redirect outcome.
    restoreIdleState();
  }

  // Start the Chat request flow from the form's submit event.
  form.addEventListener("submit", handleSubmit);
  messageInput.addEventListener("input", updateCharacterCount);
  messageInput.addEventListener("keydown", handleMessageKeydown);
  coarsePointer.addEventListener("change", updateInputHelp);
  updateInputHelp();
  updateCharacterCount();
  scrollHistoryToLatest();
})();
