"""
Users/urls.py
-------------
URL routing for the Users app.

Namespaces
----------
/api/sys/auth/   — System admin session-based two-step login
"""

from django.urls import path

from Users.views.sys_auth_views import (
    SysAdminLoginView,
    SysAdminOTPVerifyView,
    SysAdminLogoutView,
)

urlpatterns = [
    # ── System admin authentication (session + OTP) ──────────────────────
    # Step 1: Submit email + password → OTP dispatched to admin
    path("sys/auth/login/",       SysAdminLoginView.as_view(),     name="sys-auth-login"),
    # Step 2: Submit email + OTP → session created
    path("sys/auth/verify-otp/",  SysAdminOTPVerifyView.as_view(), name="sys-auth-verify-otp"),
    # Logout: flush session + mark audit record inactive
    path("sys/auth/logout/",      SysAdminLogoutView.as_view(),    name="sys-auth-logout"),
]
