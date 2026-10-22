"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.urls import include, path, re_path
from django.views.static import serve


def arquivo_de_midia(request, caminho):
    """Faturas e PDFs: só para quem entrou no sistema (o middleware de login cuida disso, D36)."""
    return serve(request, caminho, document_root=settings.MEDIA_ROOT)


@login_not_required
def arquivo_estatico(request, caminho):
    """CSS, fontes e imagens. Com DEBUG=0 o runserver/waitress não os serve sozinho (D36)."""
    return serve(request, caminho, document_root=settings.BASE_DIR / "static")


urlpatterns = [
    path("entrar/", auth_views.LoginView.as_view(), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("propostas/", include("propostas.urls")),
    path("clientes/", include("clientes.urls")),
    path("orcamentos/", include("orcamentos.urls")),
    # Fotos, datasheets, PDFs de cotação e faturas: servidos pelo próprio Django (uso interno, rede local; D05, D28).
    re_path(r"^media/(?P<caminho>.*)$", arquivo_de_midia),
]
if not settings.DEBUG:
    urlpatterns.append(re_path(r"^static/(?P<caminho>.*)$", arquivo_estatico))
