(function () {
    document.querySelectorAll("[data-password-toggle]").forEach(function (button) {
        var targetId = button.getAttribute("data-password-toggle");
        var input = document.getElementById(targetId);

        if (!input) {
            return;
        }

        button.addEventListener("click", function () {
            var isPassword = input.type === "password";
            input.type = isPassword ? "text" : "password";
            button.innerHTML = isPassword
                ? '<i data-lucide="eye-off"></i>'
                : '<i data-lucide="eye"></i>';
            if (window.ulyssesIcons) {
                window.ulyssesIcons.refresh();
            }
        });
    });
})();
