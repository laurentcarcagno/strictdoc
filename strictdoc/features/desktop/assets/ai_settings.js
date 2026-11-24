// The form of an AI server: "Load the models" asks the server for its list
// (through the application, which never shows the key again) and fills the
// choices of the field of the model. The field stays free: a server that does
// not list its models still works.
(function () {
  function loadModels(form) {
    var message = form.querySelector("[data-models-message]");
    var list = form.querySelector("datalist");
    var data = new URLSearchParams();
    ["server_id", "kind", "url", "key"].forEach(function (name) {
      data.set(name, form.elements[name].value);
    });
    if (form.elements.is_internal && form.elements.is_internal.checked) {
      data.set("is_internal", "on");
    }
    message.textContent = "";
    fetch("/settings/ai/models", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: data,
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (answer) {
        list.replaceChildren();
        answer.models.forEach(function (model) {
          var option = document.createElement("option");
          option.value = model;
          list.appendChild(option);
        });
        message.textContent =
          answer.models.length > 0
            ? answer.models.length + " ✓"
            : answer.message;
      })
      .catch(function () {
        message.textContent = "?";
      });
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-action='load-models']");
    if (button !== null) {
      loadModels(button.closest("form"));
    }
  });
})();
