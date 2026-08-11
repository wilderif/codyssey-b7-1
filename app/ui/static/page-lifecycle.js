// Revalidate server-rendered authentication state after a BFCache restore.
(() => {
  "use strict";

  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) {
      return;
    }

    document.documentElement.classList.add("page-revalidating");
    window.location.reload();
  });
})();
