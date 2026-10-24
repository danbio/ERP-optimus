// Edição do equipamento (D45): mostra só os campos do tipo escolhido.
// Cada campo de um tipo só traz data-tipos="modulo inversor"; os demais ficam sempre.
(function () {
  var tipo = document.getElementById("id_tipo");
  if (!tipo) return;

  function mostrarCamposDoTipo() {
    document.querySelectorAll("[data-tipos]").forEach(function (entrada) {
      var campo = entrada.closest(".campo");
      if (campo) campo.hidden = entrada.dataset.tipos.split(" ").indexOf(tipo.value) === -1;
    });
  }

  tipo.addEventListener("change", mostrarCamposDoTipo);
  mostrarCamposDoTipo();
})();
