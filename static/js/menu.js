// Celular (A18, D46): o menu fica recolhido; o botão "Menu" abre e fecha.
(function () {
  var botao = document.querySelector(".sidebar__menu");
  if (!botao) return;
  botao.addEventListener("click", function () {
    var aberto = botao.closest(".sidebar").classList.toggle("sidebar--aberta");
    botao.setAttribute("aria-expanded", aberto ? "true" : "false");
  });
})();
