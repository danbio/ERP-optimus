// Máscaras de digitação (D24). O servidor valida e guarda só os números;
// a máscara só ajuda o vendedor a ver o que digitou.
(function () {
  function digitos(texto, maximo) {
    return texto.replace(/\D/g, "").slice(0, maximo);
  }

  function telefone(valor) {
    var d = digitos(valor, 11);
    if (d.length <= 2) return d.length ? "(" + d : "";
    var meio = d.length === 11 ? 7 : 6;
    if (d.length <= meio) return "(" + d.slice(0, 2) + ") " + d.slice(2);
    return "(" + d.slice(0, 2) + ") " + d.slice(2, meio) + "-" + d.slice(meio);
  }

  function cpfCnpj(valor) {
    var d = digitos(valor, 14);
    if (d.length <= 11) {
      return d.replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2");
    }
    return d.replace(/^(\d{2})(\d)/, "$1.$2").replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1/$2").replace(/(\d{4})(\d)/, "$1-$2");
  }

  var mascaras = { telefone: telefone, cpf_cnpj: cpfCnpj };

  document.addEventListener("input", function (evento) {
    var campo = evento.target;
    var mascara = mascaras[campo.dataset && campo.dataset.mascara];
    if (mascara) campo.value = mascara(campo.value);
  });
})();
