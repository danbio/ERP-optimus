document.addEventListener("click", function (evento) {
  var botao = evento.target.closest("[data-remover-linha]");
  if (!botao) return;
  var linha = botao.closest(".kit-linha");
  if (!linha) return;
  linha.remove();
  var form = document.getElementById("proposta-form");
  if (form) {
    form.dispatchEvent(new Event("change", { bubbles: true }));
  }
});
