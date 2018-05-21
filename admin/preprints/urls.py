from django.conf.urls import url
from admin.preprints import views

app_name = 'admin'

urlpatterns = [
    url(r'^$', views.PreprintFormView.as_view(), name='search'),
    url(r'^(?P<guid>[a-z0-9]+)/$', views.PreprintView.as_view(), name='preprint'),
    url(r'^(?P<guid>[a-z0-9]+)/reindex_share_preprint/$', views.PreprintReindexShare.as_view(),
        name='reindex-share-preprint'),
    url(r'^(?P<guid>[a-z0-9]+)/remove_user/(?P<user_id>[a-z0-9]+)/$',
        views.PreprintRemoveContributorView.as_view(), name='remove_user'),
    url(r'^(?P<guid>[a-z0-9]+)/remove/$', views.PreprintDeleteView.as_view(),
        name='remove'),
    url(r'^(?P<guid>[a-z0-9]+)/restore/$', views.PreprintDeleteView.as_view(),
        name='restore'),
]
