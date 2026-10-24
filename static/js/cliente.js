// Cadastro de cliente (D42): o CEP preenche rua, bairro e município (ViaCEP) e o CNPJ
// preenche razão social, telefone, e-mail e endereço (BrasilAPI). A consulta é feita pelo
// navegador do vendedor e só preenche campo vazio. Sem internet, o vendedor digita.
(function () {
  var aviso = document.getElementById("busca-aviso");
  var dadosIbge = document.getElementById("municipios-ibge");
  var municipios = dadosIbge ? JSON.parse(dadosIbge.textContent) : {};

  function campo(nome) {
    return document.querySelector('[name="' + nome + '"]');
  }

  function preencher(nome, valor) {
    var el = campo(nome);
    if (el && valor && !el.value) el.value = valor;
  }

  function preencherMunicipio(codigoIbge) {
    var el = campo("municipio");
    var id = municipios[String(codigoIbge)];
    if (el && id && !el.value) el.value = id;
  }

  function avisar(texto) {
    if (aviso) aviso.textContent = texto;
  }

  function buscar(url, sucesso) {
    avisar("Buscando...");
    fetch(url)
      .then(function (resposta) {
        if (!resposta.ok) throw new Error(resposta.status);
        return resposta.json();
      })
      .then(function (dados) {
        if (dados.erro) throw new Error("não encontrado");
        sucesso(dados);
      })
      .catch(function () {
        avisar("Não deu para buscar agora. Preencha à mão.");
      });
  }

  var cep = document.querySelector("[data-busca-cep]");
  if (cep) {
    cep.addEventListener("change", function () {
      var d = cep.value.replace(/\D/g, "");
      if (d.length !== 8) return;
      buscar("https://viacep.com.br/ws/" + d + "/json/", function (dados) {
        preencher("logradouro", dados.logradouro);
        preencher("bairro", dados.bairro);
        preencher("complemento", dados.complemento);
        preencherMunicipio(dados.ibge);
        avisar("Endereço preenchido pelo CEP. Confira e complete o número.");
      });
    });
  }

  var documento = document.querySelector("[data-busca-cnpj]");
  if (documento) {
    documento.addEventListener("change", function () {
      var d = documento.value.replace(/\D/g, "");
      if (d.length !== 14) return;
      buscar("https://brasilapi.com.br/api/cnpj/v1/" + d, function (dados) {
        preencher("razao_social", dados.razao_social);
        preencher("nome", dados.nome_fantasia || dados.razao_social);
        preencher("email", dados.email);
        if (dados.ddd_telefone_1) {
          var tel = campo("telefone");
          if (tel && !tel.value) tel.value = dados.ddd_telefone_1.replace(/\D/g, "");
        }
        preencher("cep", (dados.cep || "").replace(/^(\d{5})(\d{3})$/, "$1-$2"));
        preencher("logradouro", [dados.descricao_tipo_de_logradouro, dados.logradouro].filter(Boolean).join(" "));
        preencher("numero", dados.numero);
        preencher("complemento", dados.complemento);
        preencher("bairro", dados.bairro);
        preencherMunicipio(dados.codigo_municipio_ibge);
        avisar("Dados da empresa preenchidos pela Receita (BrasilAPI). Confira antes de salvar.");
      });
    });
  }
})();
