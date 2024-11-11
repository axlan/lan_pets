from django.urls import path
from manage_pets import views
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    path("", views.home, name="home"),
    path("hello/<name>", views.hello_there, name="hello_there"),
    path("manage_pets", views.manage_pets, name="manage_pets"),
]

urlpatterns += staticfiles_urlpatterns()