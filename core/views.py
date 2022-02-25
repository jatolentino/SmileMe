from django.shortcuts import render
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model, authenticate
from .permissions import IsMember
from .serializers import (
    ChangeEmailSerializer, ChangePasswordSerializer, FileSerializer, TokenSerializer, SubscribeSerializer)
from .image_detection import detect_faces
from .models import TrackedRequest, Payment
import datetime
import math

import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# from django.contrib.auth import get_user_model
User = get_user_model()


def get_user_from_token(request):
    """ for testing """
    # print(request.META)

    # get user from the token
    # take the 2nd element from the array with .split('')[1]
    tokenKey = request.META.get('HTTP_AUTHORIZATION').split(' ')[1]
    # query:  from the token model, get the token that matches with the key of a user's token
    token = Token.objects.get(key=tokenKey)
    # query:  from the user model, get the user that matches with the token's user id
    user = User.objects.get(id=token.user_id)
    return user


class FileUploadView(APIView):
    permission_classes = (AllowAny, )
    # used to prevent spam and limit excessive requests made to the API
    throttle_scope = 'demo'

    def post(self, request, *args, **kwargs):
        # limit size of image submitted by user (size < 5 MB)
        content_length = request.META.get('CONTENT_LENGTH')  # in bytes
        # content_length is a string, convert to integer
        if int(content_length) > 5000000:  # 5 MB is 5 Million bytes
            return Response({'message:' 'File size larger than 5 Megabytes'}, status=HTTP_400_BAD_REQUEST)

        # get the file from the request via serializer
        file_serializer = FileSerializer(data=request.data)
        # if we want to access validated data from serializer, check if valid
        if file_serializer.is_valid():
            # saves file into media directory
            file_serializer.save()
            # get path of the image
            image_path = file_serializer.data.get('file')
            # pass to image_detection.py
            recognition = detect_faces(image_path)
        # recognition is a dictionary, return as response
        return Response(recognition, status=HTTP_200_OK)


class UserEmailView(APIView):
    permission_classes = (IsAuthenticated, )

    def get(self, request, *args, **kwargs):
        # get the user
        user = get_user_from_token(request)
        # get the email
        obj = {'email': user.email}

        return Response(obj)


class ChangeEmailView(APIView):
    """ can only post to this view if authenticated """
    permission_classes = (IsAuthenticated, )

    def post(self, request, *args, **kwargs):
        # grab user from request
        user = get_user_from_token(request)
        # user serializer to validate email change
        email_serializer = ChangeEmailSerializer(data=request.data)
        if email_serializer.is_valid():
            # get the data from serializer
            email = email_serializer.data.get('email')
            confirm_email = email_serializer.data.get('confirm_email')
            # save the email to the user
            if email == confirm_email:
                user.email = email
                user.save()
                return Response({'email': email}, status=HTTP_200_OK)
            # else
            return Response({'message': 'The emails DID NOT match'}, status=HTTP_400_BAD_REQUEST)
        # else, if serializer not valid
        return Response({'message': 'Incorrect data received'}, status=HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    """ can only post to this view if authenticated """
    permission_classes = (IsAuthenticated, )

    def post(self, request, *args, **kwargs):
        # grab user from request
        user = get_user_from_token(request)
        # user serializer to validate password change
        password_serializer = ChangePasswordSerializer(data=request.data)
        if password_serializer.is_valid():
            # get the data from serializer
            password = password_serializer.data.get('password')
            confirm_password = password_serializer.data.get('confirm_password')
            current_password = password_serializer.data.get('current_password')

            """ authenticates the user """
            auth_user = authenticate(
                username=user.username,
                password=current_password
            )

            """ check if valid authentication """
            if auth_user is not None:
                if password == confirm_password:
                    # set the password
                    # set_password is a method from the authenticated user object (auth_user)
                    auth_user.set_password(password)
                    # save the password
                    auth_user.save()
                    return Response(status=HTTP_200_OK)
                else:
                    return Response({'message': 'The passwords DID NOT match'}, status=HTTP_400_BAD_REQUEST)
            # else, if serializer not valid
            return Response({'message': 'Incorrect user details received'}, status=HTTP_400_BAD_REQUEST)
        return Response({'message': 'Incorrect data received'}, status=HTTP_400_BAD_REQUEST)


class UserDetailsView(APIView):
    permission_classes = (IsAuthenticated, )

    def get(self, request, *args, **kwargs):
        # grab user from request
        user = get_user_from_token(request)
        membership = user.membership
        today = datetime.datetime.now()
        # used to get 1st day of the current month, today determines current month
        month_start = datetime.date(today.year, today.month, 1)
        # timestamp__gte (timestamp is >=)
        tracked_request_count = TrackedRequest.objects \
            .filter(user=user, timestamp__gte=month_start) \
            .count()

        # if user is NOT a member
        amount_due = 0
        if user.is_member:
            # query upcoming invoices
            amount_due = stripe.Invoice.upcoming(
                customer=user.stripe_customer_id)['amount_due'] / 100  # convert from cents to dollars

        obj = {
            'membershipType': membership.get_type_display(),
            'free_trial_end_date': membership.end_date,
            'next_billing_date': membership.end_date,
            'api_request_count': tracked_request_count,
            'amount_due': amount_due
        }
        return Response(obj)


class SubscribeView(APIView):
    permission_classes = (IsAuthenticated, )

    def post(self, request, *args, **kwargs):
        # get user from request
        user = get_user_from_token(request)

        # get user membership
        membership = user.membership

        try:
            # get stripe customer
            customer = stripe.Customer.retrieve(user.stripe_customer_id)
            serializer = SubscribeSerializer(data=request.data)

            # serialize post data (stripeToken)
            if serializer.is_valid():
                # get stripeToken from serializer data
                stripe_token = serializer.data.get('stripeToken')

                # create stripe subscription
                subscription = stripe.Subscription.create(
                    customer=customer.id,
                    items=[{
                        'plan': settings.STRIPE_PLAN_ID
                    }]
                )

                # update membership with stripe subscription id
                membership.stripe_subscription_id = subscription.id
                membership.stripe_subscription_item_id = subscription['items']['data'][0]['id']
                membership.type = 'M'
                membership.start_date = datetime.datetime.now()
                # from stripe, current_period_end is a unix timestamp, convert it
                membership.end_date = datetime.datetime.fromtimestamp(
                    subscription.current_period_end
                )
                membership.save()

                # update the user subscription status
                user.is_member = True
                user.on_free_trial = False
                user.save()

                # create payment, stored in backend
                payment = Payment()
                # value is in cents, store as dollar value
                payment.amount = subscription.plan.amount / 100
                payment.user = user
                payment.save()

                return Response({'Message': 'Payment successful!'}, status=HTTP_200_OK)

            else:
                return Response({'Message': 'Incorrect data received'}, status=HTTP_400_BAD_REQUEST)

        except stripe.error.CardError as e:
            return Response({'Message': 'Your card was declined'}, status=HTTP_400_BAD_REQUEST)
        except stripe.error.StripeError as e:
            return Response({'Message': 'Error occurred. Card was NOT billed. If error persists, contact support'}, status=HTTP_400_BAD_REQUEST)
        # exception unrelated to stripe
        except Exception as e:
            return Response({'Message': 'Error occurred. We apologize. We are working on fixing the problem'}, status=HTTP_400_BAD_REQUEST)


class CancelSubscriptionView(APIView):
    permission_classes = (IsMember, )

    def post(self, request, *args, **kwargs):
        # get user from request
        user = get_user_from_token(request)
        membership = user.membership

        # update (cancel) stripe subscription
        try:
            sub = stripe.Subscription.retrieve(
                membership.stripe_subscription_id)
            sub.delete()
        except Exception as e:
            return Response({'Message': 'Error occurred. We apologize. We are working on fixing the problem'}, status=HTTP_400_BAD_REQUEST)

        # update user model from member to not member
        user.is_member = False
        user.save()

        # update membership
        membership.type = 'N'  # N in dictionary for not member
        membership.save()

        return Response({'Message': 'Subscription cancelled!'}, status=HTTP_200_OK)


class ImageRecognitionView(APIView):
    permission_classes = (IsMember, )
    # used to  spam and limit excessive requests made to the API
    throttle_scope = 'demo'

    def post(self, request, *args, **kwargs):
        # get user from request
        user = get_user_from_token(request)
        # get the membership
        membership = user.membership
        # get the file from the request via serializer
        file_serializer = FileSerializer(data=request.data)

        # none if not a member or on free trial
        usage_record_id = None
        # only create usage record if the user is a member or on free trial
        if user.is_member and not user.on_free_trial:
            usage_record = stripe.UsageRecord.create(
                # subscription item id is obtained from membership
                subscription_item=membership.stripe_subscription_item_id,
                quantity=1,
                # math.floor() prevents multiple decimals from timestamp
                timestamp=math.floor(datetime.datetime.now().timestamp()),
            )
            usage_record_id = usage_record.id

        # tracking # of requests made for billing
        tracked_request = TrackedRequest()
        tracked_request.user = user
        tracked_request.usage_record_id = usage_record_id
        tracked_request.endpoint = '/api/image-recognition/'
        tracked_request.save()

        # limit size of image submitted by user (size < 5 MB)
        content_length = request.META.get('CONTENT_LENGTH')  # in bytes
        # content_length is a string, convert to integer
        if int(content_length) > 5000000:  # 5 MB is 5 Million bytes
            return Response({'message:' 'File size larger than 5 Megabytes'}, status=HTTP_400_BAD_REQUEST)

        # if we want to access validated data from serializer, check if valid
        if file_serializer.is_valid():
            # saves file into media directory
            file_serializer.save()
            # get path of the image
            image_path = file_serializer.data.get('file')
            # pass to image_detection.py
            recognition = detect_faces(image_path)
            # recognition is a dictionary, return as response
            return Response(recognition, status=HTTP_200_OK)
        # recognition is a dictionary, return as response
        return Response({'Incorrect data received'}, status=HTTP_400_BAD_REQUEST)


class APIKeyView(APIView):
    permission_classes = (IsAuthenticated, )

    def get(self, request, *args, **kwargs):
        # get user from request
        user = get_user_from_token(request)
        token_qs = Token.objects.filter(user=user)
        if token_qs.exists():
            # many=True in case there's more than 1 token for the user
            token_serializer = TokenSerializer(token_qs, many=True)
            try:
                return Response(token_serializer.data, status=HTTP_200_OK)
            except Exception:
                return Response({'Message': 'Incorrect data received'}, status=HTTP_400_BAD_REQUEST)
        return Response({'Message': 'User does NOT exist'}, status=HTTP_400_BAD_REQUEST)
