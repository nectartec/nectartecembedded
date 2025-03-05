from rest_framework import generics
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView
from . import models, forms, serializers 

class EmbeddedListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = models.Embedded
    template_name = 'embedded_list.html'
    context_object_name = 'embeddeds'
    paginate_by = 10
    permission_required = 'embeddeds.view_embedded'

    def get_queryset(self):
        queryset = super().get_queryset()
        CLIENT_ID = self.request.GET.get('CLIENT_ID')

        if CLIENT_ID:
            queryset = queryset.filter(name__icontains=CLIENT_ID)

        return queryset


class EmbeddedCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = models.Embedded
    template_name = 'embedded_create.html'
    form_class = forms.EmbeddedForm
    success_url = reverse_lazy('embedded_list')
    permission_required = 'embeddeds.add_embedded'


class EmbeddedDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = models.Embedded
    template_name = 'embedded_detail.html'
    permission_required = 'embeddeds.view_embedded'


class EmbeddedUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = models.Embedded
    template_name = 'embedded_update.html'
    form_class = forms.EmbeddedForm
    success_url = reverse_lazy('embedded_list')
    permission_required = 'embeddeds.change_embedded'


class EmbeddedDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = models.Embedded
    template_name = 'embedded_delete.html'
    success_url = reverse_lazy('embedded_list')
    permission_required = 'embeddeds.delete_embedded'


class EmbeddedCreateListAPIView(generics.ListCreateAPIView):
    queryset = models.Embedded.objects.all()
    serializer_class = serializers.EmbeddedSerializer


class EmbeddedRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = models.Embedded.objects.all()
    serializer_class = serializers.EmbeddedSerializer



