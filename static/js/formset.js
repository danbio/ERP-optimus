// Botão "+ item" das listas de itens (formsets do Django): copia a linha modelo do <template>,
// troca __prefix__ pelo próximo índice e atualiza o TOTAL_FORMS. Sem framework (CLAUDE.md).
(function () {
  document.addEventListener("click", function (evento) {
    var botao = evento.target.closest("[data-incluir-linha]");
    if (!botao) return;
    var prefixo = botao.dataset.incluirLinha;
    var total = document.getElementById("id_" + prefixo + "-TOTAL_FORMS");
    var modelo = document.getElementById(prefixo + "-vazio");
    var corpo = botao.closest(".card").querySelector("tbody");
    var indice = parseInt(total.value, 10);
    corpo.insertAdjacentHTML("beforeend", modelo.innerHTML.replace(/__prefix__/g, String(indice)));
    total.value = indice + 1;
  });
})();
