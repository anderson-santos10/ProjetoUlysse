(function () {
    function atualizarRelogio() {
        var el = document.getElementById("hora-atual");
        if (!el) {
            return;
        }

        var agora = new Date();
        var horas = String(agora.getHours()).padStart(2, "0");
        var minutos = String(agora.getMinutes()).padStart(2, "0");
        var segundos = String(agora.getSeconds()).padStart(2, "0");
        el.textContent = horas + ":" + minutos + ":" + segundos;
    }

    atualizarRelogio();
    setInterval(atualizarRelogio, 1000);

    var buttons = Array.prototype.slice.call(
        document.querySelectorAll(".series-button[data-serie]")
    );

    function mostrarSerie(codigoSerie) {
        document.querySelectorAll(".ranking-serie").forEach(function (elemento) {
            var isActive = elemento.id === "ranking-" + codigoSerie;
            elemento.classList.toggle("active", isActive);
            elemento.hidden = !isActive;
            elemento.setAttribute("aria-hidden", isActive ? "false" : "true");
        });

        buttons.forEach(function (botao) {
            var isActive = botao.getAttribute("data-serie") === codigoSerie;
            botao.classList.toggle("active", isActive);
            botao.setAttribute("aria-selected", isActive ? "true" : "false");
            botao.setAttribute("tabindex", isActive ? "0" : "-1");
        });
    }

    window.mostrarSerie = mostrarSerie;

    buttons.forEach(function (botao, index) {
        botao.addEventListener("click", function () {
            mostrarSerie(botao.getAttribute("data-serie"));
        });

        botao.addEventListener("keydown", function (event) {
            var next = index;
            if (event.key === "ArrowRight" || event.key === "ArrowDown") {
                next = (index + 1) % buttons.length;
            } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
                next = (index - 1 + buttons.length) % buttons.length;
            } else if (event.key === "Home") {
                next = 0;
            } else if (event.key === "End") {
                next = buttons.length - 1;
            } else {
                return;
            }

            event.preventDefault();
            buttons[next].focus();
            mostrarSerie(buttons[next].getAttribute("data-serie"));
        });
    });
})();
