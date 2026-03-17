import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SMS.settings')
django.setup()

from Users.models.user import User
from Users.models.membership import OrgMembership, MembershipStatus

def debug_user(email, password):
    print(f"\n--- Debugging: {email} ---")
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        print("FAIL: User not found.")
        return

    print(f"SUCCESS: User found (Active: {user.is_active})")
    
    pw_match = user.check_password(password)
    print(f"PASSWORD CHECK: {'MATCH' if pw_match else 'FAIL'}")

    membership = OrgMembership.objects.filter(
        user=user, 
        is_system_admin=True, 
        status=MembershipStatus.ACTIVE
    ).select_related('org').first()

    if membership:
        print(f"ADMIN MEMBERSHIP: Found in Org '{membership.org.slug}' (Org Active: {membership.org.is_active})")
    else:
        print("ADMIN MEMBERSHIP: NOT FOUND or INACTIVE.")

if __name__ == "__main__":
    debug_user('bishamsinchiury1116@gmail.com', 'Bisham@0411')
    debug_user('sysadmin@educore.com', 'EduCoreAdmin789!')
