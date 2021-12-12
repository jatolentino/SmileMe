""" must create special permissions to allow subscribers, trial members,
or non members to access the correct views """
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied


class IsMember(permissions.BasePermission):

    def has_permission(self, request, view):
        # check if user authenticated, if so continue, if not, error
        if request.user.is_authenticated:
            if request.user.is_member or request.user.on_free_trial:
                return True
            else:
                raise PermissionDenied('Must be a member to make request!')
        else:
            raise PermissionDenied('Must be logged in to make request!')
