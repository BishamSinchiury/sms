# Auth & User Architecture — Full Documentation

> **Stack:** Django · PostgreSQL · JWT (simplejwt) · Session Auth (system admin)  
> **Last updated:** 2026

---

## Table of Contents

1. [Overview](#1-overview)
2. [User Types & Access Levels](#2-user-types--access-levels)
3. [Database Schema](#3-database-schema)
4. [The Membership Model (Core Concept)](#4-the-membership-model-core-concept)
5. [Role & Permission System](#5-role--permission-system)
6. [Authentication Strategy](#6-authentication-strategy)
7. [User Creation & Approval Flows](#7-user-creation--approval-flows)
8. [Dashboard Separation](#8-dashboard-separation)
9. [Security Design](#9-security-design)
10. [File Structure](#10-file-structure)
11. [Future Scaling Notes](#11-future-scaling-notes)

---

## 1. Overview

This system is a **multi-tenant SaaS platform** where each tenant is an **Organization** (e.g., a school). Every user belongs to exactly one organization, carries a role defined within that org, and accesses one of two completely separated dashboards.

**Core design principle:** A user's role is never stored on the user record itself. It lives on the **membership** record — the link between a user and their organization. This makes the system clean, auditable, and ready to scale to multi-org membership later with a single constraint change.

```
User ──► OrgMembership ──► OrgRole ──► RolePermission
                                  └──► FeatureFlag
              │
              └──► Organization
```

---

## 2. User Types & Access Levels

There are four user types. They are NOT stored as a field on the User model. They are determined by the records around the user.

| Type | Determined By | Dashboard | Auth Method | Created By |
|---|---|---|---|---|
| `super_user` | `SuperUser` table record | Terminal only | No HTTP login | Terminal script |
| `system_admin` | `OrgMembership.is_system_admin = True` | Sys Dashboard (`/sys/`) | Session + CSRF | Super user via terminal |
| `admin` | Membership role name = `admin` (system role) | General Dashboard (`/app/`) | JWT | System admin |
| `general_user` | Membership role = any custom role (Teacher, Student, etc.) | General Dashboard (`/app/`) | JWT | Self-register → approval |

### Super User

- Platform owner / developer account.
- Created by running a management command in the server terminal.
- Has **no HTTP login endpoint** — zero API surface area.
- Not a member of any organization.
- Accesses everything through Django admin and terminal management commands.
- Typically only 1–2 records exist on the entire platform.

### System Admin

- One per organization (enforced by a partial unique index on the DB).
- Manages their org's profile, users, roles, and approvals via the **Sys Dashboard**.
- Uses **session-based authentication** with CSRF protection for higher security.
- Cannot log in to the General Dashboard.
- Created by the super user via terminal/management command when a new org is provisioned.

### Admin User

- Created and assigned by the system admin.
- Has elevated access on the **General Dashboard** only.
- Uses the standard `admin` system role (locked — cannot be renamed or deleted).
- JWT authenticated.
- Can approve/reject pending general user registrations (delegated from system admin).

### General User

- Self-registers on the platform.
- Is placed in `pending` status until approved by system admin or admin user.
- Assigned a **dynamic role** (e.g., Teacher, Student) by system admin.
- JWT authenticated.
- Access is fully controlled by the permissions on their role.

---

## 3. Database Schema

### Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         organizations                               │
│  id (uuid PK)  name  slug (unique)  is_active  address  logo  ...  │
└─────────────────────────────────────────────────────────────────────┘
        │ 1                                                    │ 1
        │                                                      │
        │ ∞                                                     │ ∞
┌──────────────────┐                               ┌───────────────────┐
│    org_roles     │                               │  org_memberships  │
│  id              │◄──────────────────────────────│  id               │
│  org_id (FK)     │  role_id (FK)                 │  user_id (FK) ─┐  │
│  name            │                               │  org_id (FK)   │  │
│  is_system_role  │                               │  role_id (FK)  │  │
│  description     │                               │  status        │  │
└──────────────────┘                               │  is_system_admin  │
        │ 1                                        │  approved_by (FK) │
        │                                          └───────────────────┘
        │ ∞                                                    │
  ┌─────┴──────────────┐                                       │ ∞
  │                    │                               ┌───────┴───────┐
  ▼                    ▼                               │     users     │
┌──────────────────┐  ┌──────────────────┐            │  id (uuid PK) │
│ role_permissions │  │  feature_flags   │            │  email        │
│  id              │  │  id              │            │  password_hash│
│  role_id (FK)    │  │  role_id (FK)    │            │  first_name   │
│  module          │  │  flag_key        │            │  last_name    │
│  action          │  │  enabled         │            │  is_active    │
│  allowed         │  │  description     │            └───────────────┘
└──────────────────┘  └──────────────────┘                    │ 1
                                                               │
                                                               │ 0..1
                                                      ┌────────┴──────┐
                                                      │  super_users  │
                                                      │  id           │
                                                      │  user_id (FK) │
                                                      │  notes        │
                                                      └───────────────┘
```

### Tables Summary

| Table | Purpose |
|---|---|
| `users` | Identity only. Email + password. No role. |
| `super_users` | Marks a user as platform super user. Terminal-only. |
| `organizations` | Tenant record. One per school/institution. |
| `org_roles` | Dynamic roles per org. 3 system-reserved + unlimited custom. |
| `org_memberships` | User ↔ Org link. Carries role, status, is_system_admin. |
| `role_permissions` | Module + action grants per role. |
| `feature_flags` | Per-role feature toggles. |
| `system_admin_sessions` | Audit log of system admin login sessions. |
| `refresh_token_records` | Audit log of JWT refresh tokens. Enables revocation. |

---

## 4. The Membership Model (Core Concept)

`OrgMembership` is the most important model in the system.

```python
OrgMembership
├── user          → OneToOne → User       (enforces one-org-per-user)
├── org           → FK       → Organization
├── role          → FK       → OrgRole    (the user's role in THIS org)
├── status        → pending / active / suspended / rejected
├── is_system_admin → bool   (partial unique index: only one True per org)
├── approved_by   → FK       → User       (who approved the membership)
└── approved_at   → datetime
```

### Why OneToOne on `user`?

Right now, users belong to one org only. `OneToOneField` enforces this at the database level — it's impossible to create two memberships for the same user. When you scale to multi-org, change it to a `ForeignKey` and add `unique_together = [("user", "org")]`. That's the only migration needed.

### Checking permissions from a membership

```python
# In a view or permission class
membership = request.user.membership

# Check a module permission
if membership.has_permission("gradebook", "edit"):
    ...

# Check a feature flag
if membership.has_feature("beta_attendance_ui"):
    ...
```

---

## 5. Role & Permission System

### System-Reserved Roles (auto-created per org)

These three roles are created automatically when an org is provisioned. They cannot be renamed or deleted.

| Role Name | Purpose |
|---|---|
| `system_admin` | Reserved for the single system admin of the org |
| `admin` | General dashboard admin. Assigned by system admin. |
| `member` | Base fallback role with minimal permissions |

### Custom Roles

System admin creates custom roles via the Sys Dashboard (e.g., "Teacher", "Student", "Lab Assistant", "Librarian"). Each role is scoped to the org — two orgs can both have a "Teacher" role but they are separate records with independent permissions.

### Permission Matrix

Each role has rows in `role_permissions` — one row per (module, action) combination:

```
org_roles        role_permissions
─────────        ────────────────────────────────────
Teacher      ──► attendance.view    = True
             ──► attendance.create  = True
             ──► attendance.edit    = True
             ──► attendance.delete  = False
             ──► gradebook.view     = True
             ──► gradebook.edit     = True
             ──► reports.export     = False

Student      ──► attendance.view    = True
             ──► gradebook.view     = True
             ──► reports.export     = False
```

Adding a new module (e.g., `finance`) only requires inserting rows into `role_permissions`. No schema changes.

### Feature Flags

```
org_roles        feature_flags
─────────        ────────────────────────────────────
Teacher      ──► beta_gradebook       = True
             ──► new_attendance_ui    = True

Student      ──► beta_gradebook       = False
             ──► new_attendance_ui    = True
```

---

## 6. Authentication Strategy

The system runs **two completely separate auth paths**.

### Path A — System Admin (`/sys/` routes)

```
POST /sys/auth/login/
  └── Django session middleware
  └── CSRF token required
  └── Creates: SystemAdminSession record (audit log)
  └── Session stored: Redis (recommended) or DB

Subsequent requests:
  └── Session cookie + CSRF header
  └── Middleware verifies: session valid + user.membership.is_system_admin = True
```

Why sessions for system admin?
- Sessions can be force-expired from the server side at any time.
- CSRF protection is built in — no extra work needed.
- System admin actions (user approvals, org config) are high-value targets; session auth reduces risk of token theft.

### Path B — Admin & General Users (`/api/` routes)

```
POST /api/auth/login/
  └── Returns: { access_token, refresh_token }
  └── access_token: short-lived (15 min), in response body
  └── refresh_token: longer-lived (7 days), in HttpOnly cookie

Subsequent requests:
  └── Authorization: Bearer <access_token>
  └── Middleware verifies: token valid + membership.status = active

Token refresh:
  POST /api/auth/refresh/
  └── Reads refresh_token from HttpOnly cookie
  └── Returns new access_token
  └── Rotates refresh_token (old one blacklisted)
```

### Token Invalidation

| Scenario | Action |
|---|---|
| Logout | Refresh token blacklisted (simplejwt blacklist app) |
| Password change | `user.password_changed_at` updated; all tokens with `iat < password_changed_at` are rejected |
| Suspended membership | Middleware checks `membership.status` on every request |
| Admin force-logout | Delete `RefreshTokenRecord`, blacklist JTI |

### Super User — No HTTP Surface

```
# Super user login: no endpoint exists
# Access is exclusively via:
python manage.py shell
python manage.py <custom_management_command>
# Django admin at /django-admin/ (if enabled in production)
```

---

## 7. User Creation & Approval Flows

### Flow 1 — Provisioning a New Organization

```
super_user (terminal)
  └── python manage.py create_org --name "Greenwood High" --slug "greenwood-high"
        └── Creates: Organization record
        └── Creates: 3 system roles (system_admin, admin, member)

  └── python manage.py create_system_admin --org "greenwood-high" --email "admin@greenwood.edu"
        └── Creates: User record
        └── Creates: OrgMembership { is_system_admin=True, status=ACTIVE, role=system_admin_role }
        └── Creates: SystemAdminSession audit setup
```

### Flow 2 — Admin User Creation

```
system_admin (Sys Dashboard)
  └── Creates User with email + temp password
  └── Creates OrgMembership { role=admin_role, status=ACTIVE, approved_by=system_admin }
  └── Sends email with temp password + login link
```

No approval step — admin users are trusted and created directly.

### Flow 3 — General User Self-Registration

```
general_user (public registration page)
  └── POST /api/auth/register/
        └── Creates: User record
        └── Creates: OrgMembership { role=member_role, status=PENDING }
        └── Sends: "Registration received" email to user
        └── Sends: "New user pending approval" notification to system_admin + admin users

system_admin OR admin user
  └── Sees pending user in their dashboard
  └── Assigns a role (e.g., "Teacher")
  └── Clicks Approve → OrgMembership { status=ACTIVE, role=teacher_role, approved_by=... }
  └── User receives "Account approved" email + can now log in
```

---

## 8. Dashboard Separation

The two dashboards are completely isolated at the routing and middleware level.

### Sys Dashboard (`/sys/`)

- **Who:** System admin only
- **Auth:** Session + CSRF
- **Features:**
  - Org profile setup (name, logo, address, contact)
  - User management (view all users, pending approvals, suspend/activate)
  - Role creation and management (create custom roles, toggle permissions)
  - Feature flag management per role
  - System admin session audit log

### General Dashboard (`/app/`)

- **Who:** Admin users + all general users (students, teachers, etc.)
- **Auth:** JWT
- **Features:**
  - All school management functions (attendance, grades, timetable, etc.)
  - Admin users see additional controls (approve pending users, manage content)
  - Module visibility and actions gated by role permissions
  - Feature flags control UI feature visibility per role

### URL Routing Separation

```python
# urls.py (root)
urlpatterns = [
    path("sys/",  include("sys_dashboard.urls")),   # session auth middleware
    path("api/",  include("api.urls")),              # JWT auth middleware
    path("app/",  include("frontend.urls")),         # React SPA entry point
]
```

```python
# Middleware chain for /sys/ routes
SYS_MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "apps.auth.middleware.SystemAdminSessionMiddleware",   # custom
]

# Middleware chain for /api/ routes
API_MIDDLEWARE = [
    "apps.auth.middleware.JWTAuthMiddleware",              # custom
    "apps.auth.middleware.ActiveMembershipMiddleware",     # custom - checks status
]
```

---

## 9. Security Design

### Defense in Depth

| Layer | Control |
|---|---|
| Network | Super user accessible only via server terminal (no public endpoint) |
| Auth route separation | `/sys/` and `/api/` use completely different auth stacks |
| UUID primary keys | Prevents sequential ID enumeration attacks |
| Password storage | Django's default PBKDF2 (or swap for Argon2) |
| JWT access tokens | Short-lived (15 min) — limits blast radius of token theft |
| Refresh token rotation | Old token blacklisted on every refresh |
| HttpOnly cookie | Refresh token not accessible via JavaScript |
| CSRF protection | Required on all `/sys/` routes (session-based) |
| Membership status check | Every API request validates `membership.status = active` |
| Partial unique index | Database-level guarantee of one system_admin per org |
| `password_changed_at` | Invalidates all existing tokens on password change |
| Org isolation | All queries scoped to `org_id` — cross-org data leaks impossible via ORM |

### Key Permission Check Pattern

```python
# apps/auth/permissions.py

class HasModulePermission(BasePermission):
    """
    DRF permission class. Usage:
        permission_classes = [IsAuthenticated, HasModulePermission]
        required_permission = ("gradebook", "edit")
    """
    def has_permission(self, request, view):
        membership = getattr(request.user, "membership", None)
        if not membership or not membership.is_active:
            return False
        module, action = getattr(view, "required_permission", (None, None))
        if not module:
            return True  # no specific permission required
        return membership.has_permission(module, action)
```

---

## 10. File Structure

```
apps/
└── accounts/
    └── models/
        ├── __init__.py          # clean export surface
        ├── base.py              # TimeStampedModel (UUID PK + timestamps)
        ├── organization.py      # Organization (tenant)
        ├── user.py              # User + SuperUser
        ├── roles.py             # OrgRole + RolePermission + FeatureFlag
        ├── membership.py        # OrgMembership (core linking table)
        └── auth_session.py      # SystemAdminSession + RefreshTokenRecord
```

---

## 11. Future Scaling Notes

### Multi-org users

Change `OrgMembership.user` from `OneToOneField` to `ForeignKey`:
```python
# Before (current)
user = models.OneToOneField(User, ...)

# After (multi-org)
user = models.ForeignKey(User, ...)
class Meta:
    unique_together = [("user", "org")]
```

That's the only model change needed. All permission logic already scopes to `membership`, so it works automatically.

### Department-level access

Add a `Department` model and a FK on `OrgMembership`:
```
OrgMembership → Department (optional FK)
```
Permissions can then be checked at `(role, department)` level.

### Module subscriptions

Add an `OrgModule` table:
```
OrgModule { org, module_key, is_enabled }
```
Check org-level module access before role-level permission. Orgs subscribe to modules; roles control what they can do within those modules.

---

*This document should be kept in sync with model changes. Update the ER diagram and flow diagrams when new models are added.*
