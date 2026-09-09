(function () {
    function renderIcons() {
        if (typeof lucide !== "undefined" && typeof lucide.createIcons === "function") {
            lucide.createIcons();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", renderIcons);
    } else {
        renderIcons();
    }

    window.ulyssesIcons = {
        refresh: renderIcons,
    };
})();
