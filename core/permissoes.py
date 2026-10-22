"""Quem pode o quê (D36): o gestor altera Configurações e catálogos; o vendedor usa o resto."""

from functools import wraps

from django.shortcuts import render

GRUPO_GESTOR = "gestor"


def eh_gestor(usuario):
    return usuario.is_superuser or usuario.groups.filter(name=GRUPO_GESTOR).exists()


def so_gestor(view):
    """A view só abre para o gestor; o vendedor vê uma página explicando."""
    @wraps(view)
    def view_do_gestor(request, *args, **kwargs):
        if not eh_gestor(request.user):
            return render(request, "core/so_gestor.html", status=403)
        return view(request, *args, **kwargs)
    return view_do_gestor


def usuario(request):
    """Context processor: o menu mostra só o que o usuário pode abrir."""
    if not request.user.is_authenticated:
        return {}
    return {"eh_gestor": eh_gestor(request.user)}
