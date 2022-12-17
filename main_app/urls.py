from django.urls import path
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from . import views

app_name = 'main_app'
urlpatterns = [
    path('',views.HomeView.as_view(), name='home'),
    path('search',views.SearchView.as_view(), name='search'),
    path('login/',views.loginPage, name='login'),
    path('logout/',views.logoutPage, name='logout'),
    path('previous/',views.previousPage, name='previous-page'),
    path('viewOriginalLink/',views.view_original_link, name='view-original-link'),
    path('like/',views.product_liked, name='product-liked'),
    path('ranking/',views.ranking, name='ranking'),
    path('category/<category>', views.categoryPage, name='category-page'),
    path('<slug:slug>/<str:rank>', views.DetailPostView.as_view(), name='item-detail-page'),
    # path('about/',views.AboutView.as_view(), name='about'),
    # path('ml/',views.machine_learning, name='machine-learning'),
    # path('register/',views.registerPage, name='register'),
    # path('testerror500/',views.test_error_500, name='test-error-500'),
]
urlpatterns += staticfiles_urlpatterns()