// Máscaras de digitação (D24). O servidor valida e guarda só os números;
// a máscara só ajuda o vendedor a ver o que digitou.
(function () {
  function digitos(texto, maximo) {
    return texto.replace(/\D/g, "").slice(0, maximo);
  }

  // Tira o +55 e o zero do DDD antes de formatar, como o servidor faz, sem perder dígitos.
  function telefone(valor) {
    var d = valor.replace(/\D/g, "");
    if (valor.trim().charAt(0) === "+") {
      if (d.length <= 2) return valor;
      d = d.slice(2);
    } else if (d.length > 11 && d.slice(0, 2) === "55") {
      d = d.slice(2);
    }
    if (d.charAt(0) === "0") d = d.slice(1);
    d = d.slice(0, 11);
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

  function cep(valor) {
    return digitos(valor, 8).replace(/^(\d{5})(\d)/, "$1-$2");
  }

  var mascaras = { telefone: telefone, cpf_cnpj: cpfCnpj, cep: cep };

  document.addEventListener("input", function (evento) {
    var campo = evento.target;
    var mascara = mascaras[campo.dataset && campo.dataset.mascara];
    if (mascara) campo.value = mascara(campo.value);
  });
})();
