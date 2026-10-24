from django.db import models

from core.models import Municipio
from core.validacoes import formatar_cpf_cnpj, formatar_telefone


class Cliente(models.Model):
    nome = models.CharField(max_length=200)
    razao_social = models.CharField("razão social", max_length=200, blank=True)
    cpf_cnpj = models.CharField("CPF ou CNPJ", max_length=20, blank=True, help_text="Só os números.")
    telefone = models.CharField(max_length=30, blank=True, help_text="DDD + número, só os números.")
    email = models.EmailField("e-mail", blank=True)
    municipio = models.ForeignKey(
        Municipio, on_delete=models.PROTECT, null=True, blank=True, verbose_name="município"
    )
    # Endereço do cliente (H12, D42): todos opcionais. O da instalação fica na UC.
    cep = models.CharField("CEP", max_length=9, blank=True)
    logradouro = models.CharField("rua", max_length=200, blank=True)
    numero = models.CharField("número", max_length=20, blank=True)
    complemento = models.CharField(max_length=100, blank=True)
    bairro = models.CharField(max_length=100, blank=True)
    observacoes = models.TextField("observações", blank=True)
    criado_em = models.DateTimeField("cadastrado em", auto_now_add=True)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @property
    def cpf_cnpj_formatado(self):
        """CPF ou CNPJ com pontos, barra e traço, para a tela e o PDF."""
        return formatar_cpf_cnpj(self.cpf_cnpj)

    @property
    def telefone_formatado(self):
        """Telefone no formato (63) 99999-1234."""
        return formatar_telefone(self.telefone)

    @property
    def endereco_completo(self):
        """"Rua 7, 120, casa 2, Centro, CEP 77400-000" com o que estiver preenchido."""
        partes = [self.logradouro, self.numero, self.complemento, self.bairro]
        texto = ", ".join(p for p in partes if p)
        if self.cep:
            texto = f"{texto}, CEP {self.cep}" if texto else f"CEP {self.cep}"
        return texto


class UnidadeConsumidora(models.Model):
    class Classe(models.TextChoices):
        B1 = "B1", "B1 residencial"
        B2 = "B2", "B2 rural"
        B3 = "B3", "B3 comercial/outros"

    class Ligacao(models.TextChoices):
        MONO = "mono", "Monofásica (30 kWh)"
        BI = "bi", "Bifásica (50 kWh)"
        TRI = "tri", "Trifásica (100 kWh)"

    DISPONIBILIDADE_KWH = {Ligacao.MONO: 30, Ligacao.BI: 50, Ligacao.TRI: 100}

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="unidades_consumidoras")
    numero_uc = models.CharField("número da UC", max_length=30)
    endereco = models.CharField("endereço", max_length=255)
    # null só para a migration de UCs antigas com município digitado errado; o formulário exige.
    municipio = models.ForeignKey(Municipio, on_delete=models.PROTECT, null=True, verbose_name="município")
    concessionaria = models.CharField("concessionária", max_length=120, blank=True)  # a do município (D47)
    classe = models.CharField(max_length=2, choices=Classe.choices)
    ligacao = models.CharField("ligação", max_length=4, choices=Ligacao.choices)

    class Meta:
        verbose_name = "Unidade consumidora"
        verbose_name_plural = "Unidades consumidoras"

    def __str__(self):
        return f"{self.numero_uc} — {self.cliente.nome}"

    @property
    def uf(self):
        """UF do município da UC, ou vazio sem município."""
        return self.municipio.uf if self.municipio else ""

    @property
    def disponibilidade_kwh(self):
        """Custo de disponibilidade da ligação, em kWh/mês (30, 50 ou 100)."""
        return self.DISPONIBILIDADE_KWH[self.ligacao]
