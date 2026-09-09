(function () {
    document.querySelectorAll("form[data-loading-form]").forEach(function (form) {
        if (form.hasAttribute("data-confirm-finalize")) {
            return;
        }
        form.addEventListener("submit", function () {
            form.querySelectorAll("button[type='submit']").forEach(function (button) {
                if (button.disabled) {
                    return;
                }
                button.dataset.originalLabel = button.innerHTML;
                button.disabled = true;
                button.classList.add("is-loading");
                if (!button.querySelector(".btn-loading-label")) {
                    var span = document.createElement("span");
                    span.className = "btn-loading-label";
                    span.textContent = " Aguarde…";
                    button.appendChild(span);
                }
            });
        });
    });
})();
