from django.urls import path
from . import views 
 
urlpatterns = [
    path('clienteshtmls/list/', views.ClientehtmlListView.as_view(), name='clienteshtml_list'),
    path('clienteshtmls/create/', views.ClientehtmlCreateView.as_view(), name='clienteshtml_create'),
    path('clienteshtmls/<int:pk>/detail/', views.ClientehtmlDetailView.as_view(), name='clienteshtml_detail'),
    path('clienteshtmls/<int:pk>/update/', views.ClientehtmlUpdateView.as_view(), name='clienteshtml_update'),
    path('clienteshtmls/<int:pk>/delete/', views.ClientehtmlDeleteView.as_view(), name='clienteshtml_delete'),

]
