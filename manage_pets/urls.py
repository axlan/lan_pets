from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import path

from manage_pets import views

urlpatterns = [
    path("", views.manage_pets, name="manage_pets"),
    path("hello/<name>", views.hello_there, name="hello_there"),
    path("manage_pets", views.manage_pets, name="manage_pets"),
    path("view_pet/<name>", views.view_pet, name="view_pet"),
    path("delete_pet/<name>", views.delete_pet, name="delete_pet"),
    path("edit_pet/<name>", views.edit_pet, name="edit_pet"),
    path("view_relationships", views.view_relationships, name="view_relationships"),
]

urlpatterns += staticfiles_urlpatterns()
