from django.db import models


class Cliente(models.Model):
    nome = models.CharField(max_length=200)
    razao_social = models.CharField(max_length=200, blank=True)
    cpf_cnpj = models.CharField("CPF/CNPJ", max_length=20, blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


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
    endereco = models.CharField(max_length=255)
    municipio = models.CharField(max_length=120)
    uf = models.CharField(max_length=2)
    concessionaria = models.CharField(max_length=120, default="Energisa TO")
    classe = models.CharField(max_length=2, choices=Classe.choices)
    ligacao = models.CharField(max_length=4, choices=Ligacao.choices)

    class Meta:
        verbose_name = "Unidade consumidora"
        verbose_name_plural = "Unidades consumidoras"

    def __str__(self):
        return f"{self.numero_uc} — {self.cliente.nome}"

    @property
    def disponibilidade_kwh(self):
        return self.DISPONIBILIDADE_KWH[self.ligacao]
