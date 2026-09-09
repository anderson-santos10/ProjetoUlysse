(function () {
    var searchInput = document.getElementById("searchInput");
    var toast = document.getElementById("toast");

    function filterStudents() {
        if (!searchInput) {
            return;
        }

        var input = searchInput.value.toLowerCase().trim();
        var rows = document.querySelectorAll(".student-row");
        var noResults = document.getElementById("noResults");
        var table = document.getElementById("studentsTable");
        var counter = document.getElementById("studentCount");
        var tableHead = document.querySelector("#studentsTable thead");
        var visibleCount = 0;

        rows.forEach(function (row) {
            var nameEl = row.querySelector(".student-name");
            var raEl = row.querySelector(".badge-ra");
            var serieEl = row.querySelector(".badge-serie");
            var studentName = nameEl ? nameEl.textContent.toLowerCase() : "";
            var studentRA = raEl ? raEl.textContent.toLowerCase() : "";
            var studentSerie = serieEl ? serieEl.textContent.toLowerCase() : "";

            if (
                studentName.indexOf(input) !== -1 ||
                studentRA.indexOf(input) !== -1 ||
                studentSerie.indexOf(input) !== -1
            ) {
                row.style.display = "";
                visibleCount += 1;
            } else {
                row.style.display = "none";
            }
        });

        if (counter) {
            counter.textContent = visibleCount;
        }

        if (noResults && table) {
            if (visibleCount === 0) {
                if (tableHead) {
                    tableHead.style.display = "none";
                }
                noResults.style.display = "block";
            } else {
                if (tableHead) {
                    tableHead.style.display = "table-header-group";
                }
                noResults.style.display = "none";
            }
        }
    }

    function copyFromElement(element) {
        var raNode = element.querySelector(".ra-text");
        var cleanRAText = raNode
            ? raNode.textContent.trim()
            : Array.prototype.filter
                .call(element.childNodes, function (node) {
                    return node.nodeType === 3;
                })
                .map(function (node) {
                    return node.textContent;
                })
                .join("")
                .trim();

        if (!cleanRAText || !navigator.clipboard) {
            return;
        }

        navigator.clipboard.writeText(cleanRAText).then(function () {
            if (!toast) {
                return;
            }
            toast.classList.add("show");
            setTimeout(function () {
                toast.classList.remove("show");
            }, 2500);
        }).catch(function () {
            alert("Não foi possível copiar o RA automaticamente.");
        });
    }

    if (searchInput) {
        searchInput.addEventListener("input", filterStudents);
        searchInput.addEventListener("keyup", filterStudents);
    }

    document.querySelectorAll("[data-copy-ra]").forEach(function (element) {
        element.addEventListener("click", function () {
            copyFromElement(element);
        });

        element.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                copyFromElement(element);
            }
        });
    });
})();
