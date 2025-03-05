from rest_framework import generics
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView
from . import models, forms

class ClientehtmlListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = models.Clienteshtml
    template_name = 'clienteshtml_list.html'
    context_object_name = 'clientehtmls'
    paginate_by = 10
    permission_required = 'clientehtmls.view_clientehtml'

    def get_queryset(self):
        queryset = super().get_queryset()
        TOKEN_UUID = self.request.GET.get('TOKEN_UUID')

        if TOKEN_UUID:
            queryset = queryset.filter(name__icontains=TOKEN_UUID)

        return queryset


class ClientehtmlCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = models.Clienteshtml
    template_name = 'Clienteshtml_create.html'
    form_class = forms.ClientehtmlForm
    success_url = reverse_lazy('clientehtml_list')
    permission_required = 'clientehtmls.add_clientehtml'


class ClientehtmlDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = models.Clienteshtml
    template_name = 'clienteshtml_detail.html'
    permission_required = 'clientehtmls.view_clientehtml'


class ClientehtmlUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = models.Clienteshtml
    template_name = 'clienteshtml_update.html'
    form_class = forms.ClientehtmlForm
    success_url = reverse_lazy('clientehtml_list')
    permission_required = 'clientehtmls.change_clientehtml'


class ClientehtmlDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = models.Clienteshtml
    template_name = 'clienteshtml_delete.html'
    success_url = reverse_lazy('clientehtml_list')
    permission_required = 'clientehtmls.delete_clientehtml'



