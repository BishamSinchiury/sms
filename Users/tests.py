from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from Users.models.user import User
from Users.models.roles import OrgRole, ADMIN_ROLE, MEMBER_ROLE, SYSTEM_ADMIN_ROLE
from Users.models.membership import OrgMembership, MembershipStatus
from Orgs.models.organization import Organization

class UserApprovalFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Setup Organization
        self.org = Organization.objects.create(name="Test Org", slug="test-org")
        
        # Setup Roles
        self.sys_admin_role = OrgRole.objects.create(org=self.org, name=SYSTEM_ADMIN_ROLE, is_system_role=True)
        self.admin_role = OrgRole.objects.create(org=self.org, name=ADMIN_ROLE, is_system_role=True)
        self.member_role = OrgRole.objects.create(org=self.org, name=MEMBER_ROLE, is_system_role=True)
        self.teacher_role = OrgRole.objects.create(org=self.org, name="Teacher", is_system_role=False)
        
        # Setup Sys Admin User
        self.sys_admin = User.objects.create_user(email="sysadmin@test.com", password="password")
        self.sys_admin_membership = OrgMembership.objects.create(
            user=self.sys_admin,
            org=self.org,
            role=self.sys_admin_role,
            status=MembershipStatus.ACTIVE,
            is_system_admin=True
        )

    def test_registration_creates_pending_membership(self):
        url = reverse('auth-register')
        data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "johndoe@test.com",
            "password": "password123",
            "role_id": self.teacher_role.id
        }
        res = self.client.post(url, data)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        
        user = User.objects.get(email="johndoe@test.com")
        self.assertEqual(user.first_name, "John")
        
        membership = user.membership
        self.assertEqual(membership.status, MembershipStatus.PENDING)
        self.assertEqual(membership.role, self.teacher_role)

    def test_profile_update_changes_status_to_waiting(self):
        # Create a user with PENDING status manually
        user = User.objects.create_user(email="pending@test.com", password="password123")
        membership = OrgMembership.objects.create(
            user=user, org=self.org, role=self.teacher_role, status=MembershipStatus.PENDING
        )
        
        # We need to authenticate for the profile update
        self.client.force_authenticate(user=user)
        url = reverse('user-profile-update')
        data = {
            "first_name": "Updated",
            "last_name": "User",
            "phone_number": "1234567890"
        }
        res = self.client.patch(url, data)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        
        membership.refresh_from_db()
        self.assertEqual(membership.status, MembershipStatus.WAITING_APPROVAL)
        
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Updated")
        self.assertEqual(user.phone_number, "1234567890")

    def test_sys_admin_approve_user(self):
        # Create user waiting approval
        user = User.objects.create_user(email="waiting@test.com", password="password123")
        membership = OrgMembership.objects.create(
            user=user, org=self.org, role=self.teacher_role, status=MembershipStatus.WAITING_APPROVAL
        )
        
        # Authenticate sys admin
        self.client.force_authenticate(user=self.sys_admin)
        url = reverse('sys-users-approve', kwargs={'pk': membership.id})
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        
        membership.refresh_from_db()
        self.assertEqual(membership.status, MembershipStatus.ACTIVE)
        self.assertEqual(membership.approved_by, self.sys_admin)

    def test_sys_admin_reject_user(self):
        # Create user waiting approval
        user = User.objects.create_user(email="reject@test.com", password="password123")
        membership = OrgMembership.objects.create(
            user=user, org=self.org, role=self.teacher_role, status=MembershipStatus.WAITING_APPROVAL
        )
        
        # Authenticate sys admin
        self.client.force_authenticate(user=self.sys_admin)
        url = reverse('sys-users-reject', kwargs={'pk': membership.id})
        res = self.client.post(url, {"reason": "Not a real person"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        
        membership.refresh_from_db()
        self.assertEqual(membership.status, MembershipStatus.REJECTED)
        self.assertEqual(membership.rejection_reason, "Not a real person")
