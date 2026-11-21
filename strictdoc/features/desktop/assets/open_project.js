// The wait of the opening of a project: it asks the server for the state of
// the job until the job is done, then moves the window to the project.
(function () {
  "use strict";

  var job = document.querySelector("[data-status-url]");
  if (job === null) {
    return;
  }
  var statusUrl = job.getAttribute("data-status-url");
  var progress = document.getElementById("job-progress");
  var errorBox = document.getElementById("job-error");
  var errorMessage = document.getElementById("job-error-message");
  var POLL_DELAY_MS = 400;

  function showStep(step) {
    progress.querySelectorAll("[data-step]").forEach(function (element) {
      element.hidden = element.getAttribute("data-step") !== step;
    });
  }

  function onStatus(status) {
    if (status.state === "done") {
      window.location.href = status.url;
      return;
    }
    if (status.state === "failed") {
      progress.hidden = true;
      errorMessage.textContent = status.message;
      errorBox.hidden = false;
      return;
    }
    showStep(status.step);
    window.setTimeout(poll, POLL_DELAY_MS);
  }

  function poll() {
    window
      .fetch(statusUrl, { cache: "no-store" })
      .then(function (response) {
        return response.json();
      })
      .then(onStatus)
      .catch(function () {
        window.setTimeout(poll, POLL_DELAY_MS * 2);
      });
  }

  poll();
})();
