from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path,include
from rest_framework.routers import SimpleRouter
from drf_spectacular.views import SpectacularAPIView
from cashflows import views, entity_views

router=SimpleRouter(trailing_slash=False)
router.register('runs',views.RunViewSet,basename='run')
router.register('entities',entity_views.EntityViewSet,basename='entity')
urlpatterns=[
    path('',views.workspace,name='workspace'),
    path('admin/',admin.site.urls),
    path('accounts/login/',auth_views.LoginView.as_view(),name='login'),
    path('accounts/logout/',auth_views.LogoutView.as_view(),name='logout'),
    path('api-auth/',include('rest_framework.urls')),
    path('api-docs',views.api_guide,name='api-guide'),
    path('api/v1/session',entity_views.session_info,name='session'),
    path('api/v1/validate',entity_views.validate_portfolio,name='validate'),
    path('api/v1/health',views.health,name='health'),
    path('api/v1/sample',views.sample_input,name='sample'),
    path('api/v1/schema',SpectacularAPIView.as_view(),name='schema'),
    path('api/v1/',include(router.urls)),
]
