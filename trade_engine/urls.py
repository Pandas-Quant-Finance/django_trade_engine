from django.urls import path, include
from trade_engine import views


urlpatterns = [
    # manual api
    path('', views.index, name='index'),
]
