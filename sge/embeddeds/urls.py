from django.urls import path
from . import views , get_embedded_html
'''http://localhost:8000/api/v1/embeddeds/?email=usuario@exemplo.com'''
''''''
urlpatterns = [
    path('embeddeds/list/', views.EmbeddedListView.as_view(), name='embedded_list'),
    path('embeddeds/create/', views.EmbeddedCreateView.as_view(), name='embedded_create'),
    path('embeddeds/<int:pk>/detail/', views.EmbeddedDetailView.as_view(), name='embedded_detail'),
    path('embeddeds/<int:pk>/update/', views.EmbeddedUpdateView.as_view(), name='embedded_update'),
    path('embeddeds/<int:pk>/delete/', views.EmbeddedDeleteView.as_view(), name='embedded_delete'),

    path('api/v1/embeddeds/', views.EmbeddedCreateListAPIView.as_view(), name='embedded-create-list-api-view'),
    path('api/v1/embeddeds/<int:pk>/', views.EmbeddedRetrieveUpdateDestroyAPIView.as_view(), name='embedded-detail-api-view'),
    path('api/v1/embeddeds/email/', get_embedded_html.get_embedded_html, name='embedded_api'),
]
