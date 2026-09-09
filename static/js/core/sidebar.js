(function () {
    var toggle = document.querySelector("[data-sidebar-toggle]");
    var sidebar = document.querySelector("[data-sidebar]");
    var overlay = document.querySelector("[data-sidebar-overlay]");

    if (!toggle || !sidebar || !overlay) {
        return;
    }

    function setOpen(open) {
        sidebar.classList.toggle("is-open", open);
        sidebar.classList.toggle("is-mobile-open", open);
        overlay.classList.toggle("is-open", open);
        overlay.classList.toggle("is-mobile-open", open);
        document.body.classList.toggle("sidebar-is-open", open);
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        toggle.setAttribute("aria-label", open ? "Fechar menu" : "Abrir menu");
    }

    toggle.addEventListener("click", function () {
        setOpen(!sidebar.classList.contains("is-open"));
    });

    overlay.addEventListener("click", function () {
        setOpen(false);
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            setOpen(false);
        }
    });
})();
