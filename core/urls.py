from django.urls import path
from .views import (FileUploadView, ChangeEmailView,
                    UserEmailView, ChangePasswordView, UserDetailsView,
                    SubscribeView, ImageRecognitionView, APIKeyView, CancelSubscriptionView)

app_name = "core"

urlpatterns = [

    path("demo/", FileUploadView.as_view(), name="file-upload-demo"),
    path("change-email/", ChangeEmailView.as_view(), name="change-email"),
    path("email/", UserEmailView.as_view(), name="email"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("billing/", UserDetailsView.as_view(), name="billing"),
    path("subscribe/", SubscribeView.as_view(), name="subscribe"),
    path("upload/", ImageRecognitionView.as_view(), name="image-recognition"),
    path("api-key/", APIKeyView.as_view(), name="api-key"),
    path("cancel-subscription/", CancelSubscriptionView.as_view(),
         name="cancel-subscription"),
]
