(function () {
    function formatarHms(totalSegundos) {
        var segundosRestantes = Math.max(0, Number(totalSegundos) || 0);
        var horas = Math.floor(segundosRestantes / 3600);
        var minutos = Math.floor((segundosRestantes % 3600) / 60);
        var segundos = segundosRestantes % 60;
        return (
            String(horas).padStart(2, "0") +
            ":" +
            String(minutos).padStart(2, "0") +
            ":" +
            String(segundos).padStart(2, "0")
        );
    }

    function iniciarContadorBloqueio(segundosIniciais) {
        var contador = document.getElementById("contador-bloqueio");
        if (!contador) {
            return;
        }

        var segundosRestantes = Number(segundosIniciais);
        if (Number.isNaN(segundosRestantes)) {
            segundosRestantes = Number(contador.getAttribute("data-segundos-restantes") || 0);
        }

        function atualizarBloqueio() {
            if (segundosRestantes <= 0) {
                contador.textContent = "00:00:00";
                setTimeout(function () {
                    location.reload();
                }, 1000);
                return;
            }

            contador.textContent = formatarHms(segundosRestantes);
            segundosRestantes -= 1;
        }

        atualizarBloqueio();
        setInterval(atualizarBloqueio, 1000);
    }

    var root = document.getElementById("quiz-root");
    var contadorPainel = document.getElementById("contador-bloqueio");

    if (!root && contadorPainel) {
        iniciarContadorBloqueio(contadorPainel.getAttribute("data-segundos-restantes"));
        return;
    }

    if (!root) {
        return;
    }

    var cronometroAtivo = root.getAttribute("data-cronometro") === "1";
    var bloqueado = root.getAttribute("data-bloqueado") === "1";
    var finalizado = root.getAttribute("data-finalizado") === "1";
    var segundosRestantes = Number(root.getAttribute("data-segundos-restantes") || 0);

    if (cronometroAtivo) {
        var tempoInicial = localStorage.getItem("ulysses_tempo_inicio");

        if (!tempoInicial) {
            tempoInicial = Date.now();
            localStorage.setItem("ulysses_tempo_inicio", tempoInicial);
        }

        function atualizarCronometro() {
            var agora = Date.now();
            var segundos = Math.floor((agora - Number(tempoInicial)) / 1000);
            var minutos = Math.floor(segundos / 60);
            var segundosRestantesRelogio = segundos % 60;
            var minutosFormatados = String(minutos).padStart(2, "0");
            var segundosFormatados = String(segundosRestantesRelogio).padStart(2, "0");
            var cronometro = document.getElementById("cronometro");

            if (cronometro) {
                cronometro.textContent = minutosFormatados + ":" + segundosFormatados;
            }

            var campoTempo = document.getElementById("tempo_segundos");
            if (campoTempo) {
                campoTempo.value = segundos;
            }
        }

        atualizarCronometro();
        setInterval(atualizarCronometro, 1000);
    }

    if (bloqueado) {
        iniciarContadorBloqueio(segundosRestantes);
    }

    if (finalizado) {
        localStorage.removeItem("ulysses_tempo_inicio");
    }

    var formulario = document.getElementById("form-questao");

    function atualizarTempoOculto() {
        var campoTempo = document.getElementById("tempo_segundos");
        if (!campoTempo) {
            return;
        }

        var inicio = localStorage.getItem("ulysses_tempo_inicio");
        if (inicio) {
            var agora = Date.now();
            var segundos = Math.floor((agora - Number(inicio)) / 1000);
            campoTempo.value = segundos;
        }
    }

    if (formulario) {
        formulario.addEventListener("submit", atualizarTempoOculto);
    }

    document.querySelectorAll("[data-confirm-finalize]").forEach(function (formFinalizar) {
        formFinalizar.addEventListener("submit", function (event) {
            var botao = formFinalizar.querySelector("[data-finalize-submit]");
            if (botao && botao.disabled) {
                event.preventDefault();
                return;
            }

            var confirmado = window.confirm(
                "Tem certeza que deseja finalizar?\n\nDepois de finalizar, esta tentativa não poderá ser alterada."
            );
            if (!confirmado) {
                event.preventDefault();
                return;
            }

            atualizarTempoOculto();
            if (botao) {
                botao.disabled = true;
                botao.classList.add("is-loading");
            }
        });
    });

    document.querySelectorAll("[data-finalize-submit]").forEach(function (botao) {
        var formFinalizar = botao.closest("form");
        if (!formFinalizar || formFinalizar.hasAttribute("data-confirm-finalize")) {
            return;
        }
        formFinalizar.addEventListener("submit", function (event) {
            if (botao.disabled) {
                event.preventDefault();
                return;
            }
            botao.disabled = true;
        });
    });
})();
