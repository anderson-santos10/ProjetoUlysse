(function () {
    document.querySelectorAll("input[type='file'][data-image-preview]").forEach(function (input) {
        var alvo = document.getElementById(input.getAttribute("data-image-preview"));
        if (!alvo) {
            return;
        }
        var img = alvo.querySelector("img");
        input.addEventListener("change", function () {
            var arquivo = input.files && input.files[0];
            if (!arquivo || arquivo.type.indexOf("image/") !== 0) {
                alvo.hidden = true;
                img.removeAttribute("src");
                return;
            }
            var leitor = new FileReader();
            leitor.onload = function () {
                img.src = leitor.result;
                alvo.hidden = false;
            };
            leitor.readAsDataURL(arquivo);
        });
    });
})();
