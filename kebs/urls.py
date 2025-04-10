from django.urls import path
from . import views
from rest_framework.routers import DefaultRouter

# Create a router for RESTful API endpoints
router = DefaultRouter()
app_name = 'kebs'
urlpatterns = [
    # Dashboard and main views
    path('', views.dashboard, name='dashboard'),
    path('samples/', views.sample_list, name='sample_list'),
    path('samples/create/', views.create_sample, name='create_sample'),
    path('samples/<int:sample_id>/', views.sample_detail, name='sample_detail'),
    path('samples/<int:sample_id>/add-test-result/', views.add_test_result, name='add_test_result'),
    path('samples/<int:sample_id>/add-test-result-crispy/', views.add_test_result_crispy,
         name='add_test_result_crispy'),

    # Data management and tracking
    path('data-management/', views.data_management, name='data_management'),
    path('sample-tracking/', views.sample_tracking, name='sample_tracking'),
    path('test-results/', views.test_results, name='test_results'),
    path('test-results/<int:sample_id>/', views.test_results_detail, name='test_results_detail'),

    # Label generation and download
    path('generate-label/', views.generate_label, name='generate_label'),
    path('generate-label-page/', views.generate_label_page, name='generate_label_page'),
    path('labels/<int:label_id>/download/', views.download_label, name='download_label'),
    path('test-results-pdf/<int:sample_id>/', views.view_test_results_pdf, name='view_test_results_pdf'),

    # API endpoints
    path('api/samples/', views.api_sample_list, name='api_sample_list'),
    path('api/samples/generate-label/', views.api_generate_label, name='api_generate_label'),
]

# Add the router URLs
urlpatterns += router.urls