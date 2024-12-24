from django.urls import path
from manage_pets import views
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    path("", views.manage_pets, name="manage_pets"),
    path("hello/<name>", views.hello_there, name="hello_there"),
    path("manage_pets", views.manage_pets, name="manage_pets"),
    path("view_pet/<name>", views.view_pet, name="view_pet"),
    path("delete_pet/<name>", views.delete_pet, name="delete_pet"),
    path("edit_pet/<name>", views.edit_pet, name="edit_pet"),
]

urlpatterns += staticfiles_urlpatterns()
