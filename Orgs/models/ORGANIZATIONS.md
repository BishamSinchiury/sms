# Organizations App — Architecture Documentation

> **App:** `apps.organizations`  
> **Database:** PostgreSQL  
> **Depends on:** `apps.core` (TimeStampedModel)  
> **Depended on by:** `apps.accounts`, `apps.academic`, all other tenant-scoped apps

---

## Table of Contents

1. [Overview](#1-overview)
2. [Model Structure](#2-model-structure)
3. [Database Schema](#3-database-schema)
4. [Domain-Based Authentication](#4-domain-based-authentication)
5. [Public vs Private Data Split](#5-public-vs-private-data-split)
6. [Organization Provisioning Flow](#6-organization-provisioning-flow)
7. [Public Landing Page](#7-public-landing-page)
8. [File Storage](#8-file-storage)
9. [Security Considerations](#9-security-considerations)
10. [Future Scaling Notes](#10-future-scaling-notes)

---

## 1. Overview

The `organizations` app is the **multi-tenancy foundation** of the platform. Every other app (accounts, academic, etc.) scopes its data to an `Organization` record.

The app is split into four focused models:

| Model | Purpose | Visibility |
|---|---|---|
| `Organization` | Lean anchor/tenant record | Internal only |
| `OrgDomain` | Domain registry for auth routing | Internal only |
| `OrganizationProfile` | Public-facing school info | **Public** |
| `OrganizationLegal` | Private legal & compliance data | Sys admin only |

**Core philosophy:** The `Organization` model stays deliberately minimal. It is the immutable anchor everything else points to. Rich data lives in the related models where it belongs — public data in `OrganizationProfile`, sensitive data in `OrganizationLegal`.

---

## 2. Model Structure

```
Organization  (anchor — slug, is_active)
    │
    ├── OrgDomain (1 primary + N aliases)
    │       domain, is_primary, is_verified
    │
    ├── OrganizationProfile  (OneToOne — PUBLIC)
    │       name, logo, motto, address, contact, social
    │
    └── OrganizationLegal    (OneToOne — PRIVATE)
            owner identity, registration, tax, accreditation
```

### Organization

The anchor tenant record. Contains only:
- `slug` — immutable URL-safe identifier (set at creation, never changed)
- `is_active` — master on/off switch for the entire org
- `deactivated_at` / `deactivation_reason` — soft-deletion audit trail

Everything else delegates to related models.

### OrgDomain

Maps domain names to organizations. Enables domain-based auth routing.

- One `is_primary=True` domain per org (DB-enforced)
- Zero or more alias domains
- `is_verified` flag — only verified domains are used for auth routing
- Global uniqueness on `domain` — one domain can never point to two orgs

### OrganizationProfile

All fields shown on the public landing page. Managed by system admin via Sys Dashboard.

Key sections:
- **Core identity** — name, short name, school type, tagline, description, established year
- **Branding** — logo, favicon, cover image, primary color
- **Physical address** — address lines, city, state, postal code, country
- **Contact** — primary/secondary phone, primary/admissions email, website
- **Social media** — Facebook, Twitter, Instagram, LinkedIn, YouTube

Includes a `profile_completion_percent` property to prompt system admin on first login.

### OrganizationLegal

Private data — never exposed publicly. Managed by system admin, visible to super user.

Key sections:
- **Owner identity** — full name, title, ID type, ID number
- **Registration** — number, date, registering body, document upload, expiry
- **Tax** — tax ID, VAT registration, VAT number
- **Accreditation** — status, body, certificate number, validity dates, document upload

---

## 3. Database Schema

```
┌──────────────────────────────────┐
│          organizations           │
│  id (uuid PK)                    │
│  slug (unique)                   │
│  is_active                       │
│  deactivated_at                  │
│  deactivation_reason             │
│  created_at / updated_at         │
└──────────────────────────────────┘
         │ 1
         ├─────────────────────────────────────────────────────┐
         │ ∞                          │ 1              │ 1      │ 1
┌────────┴──────────┐   ┌────────────┴──────┐   ┌────┴──────────────────┐
│    org_domains    │   │    org_profiles    │   │      org_legal        │
│  id               │   │  id               │   │  id                   │
│  org_id (FK)      │   │  org_id (FK, O2O) │   │  org_id (FK, O2O)     │
│  domain (unique)  │   │  name             │   │  owner_full_name      │
│  is_primary       │   │  short_name       │   │  owner_id_number      │
│  is_verified      │   │  school_type      │   │  registration_number  │
│  verified_at      │   │  tagline          │   │  registration_date    │
│  notes            │   │  description      │   │  registered_with      │
└───────────────────┘   │  established_year │   │  registration_doc     │
                        │  logo             │   │  tax_id_number        │
                        │  favicon          │   │  vat_number           │
                        │  cover_image      │   │  accreditation_status │
                        │  primary_color    │   │  accreditation_body   │
                        │  address_line_1   │   │  accreditation_doc    │
                        │  address_line_2   │   │  internal_notes       │
                        │  city             │   └───────────────────────┘
                        │  state_province   │
                        │  postal_code      │
                        │  country          │
                        │  phone_primary    │
                        │  phone_secondary  │
                        │  email_primary    │
                        │  email_admissions │
                        │  website          │
                        │  facebook_url     │
                        │  twitter_url      │
                        │  instagram_url    │
                        │  linkedin_url     │
                        │  youtube_url      │
                        └───────────────────┘
```

### Key Constraints

| Constraint | Table | Rule |
|---|---|---|
| `uq_one_primary_domain_per_org` | `org_domains` | Only one `is_primary=True` per org (partial unique index) |
| `unique` on `domain` | `org_domains` | One domain globally maps to one org only |
| `OneToOneField` | `org_profiles` | One profile per org |
| `OneToOneField` | `org_legal` | One legal record per org |

---

## 4. Domain-Based Authentication

This is the core security mechanism that prevents cross-org credential reuse.

### How it works

```
1. User visits:     https://greenwood.edu/login
                    (or https://cityschool.edu/login)

2. Frontend sends:  POST /api/auth/login/
                    Host: greenwood.edu
                    Body: { email, password }

3. Backend runs:
   org = OrgDomain.resolve_org("greenwood.edu")
   if org is None → 404 (unknown or unverified domain)
   if not org.is_active → 403 (org suspended)

4. Auth proceeds:
   user = authenticate(email=email, password=password)
   membership = user.membership
   if membership.org != org → 403 (valid credentials, wrong org)

5. Login succeeds only if:
   ✓ Domain is verified + active
   ✓ Credentials are valid
   ✓ User belongs to THIS org
   ✓ Membership status is ACTIVE
```

### Why this matters

Without domain-based auth, a system admin with credentials from School A could log in at School B's URL if they somehow knew the URL. Domain binding makes this structurally impossible.

### OrgDomain.resolve_org()

Built-in class method for use in auth middleware:

```python
# In auth middleware or login view
from apps.organizations.models import OrgDomain

org = OrgDomain.resolve_org(request.get_host())
if org is None:
    return Response(status=404)
```

### Domain Verification Flow

```
super_user (terminal)
  └── Registers domain:  python manage.py add_org_domain --org greenwood-high --domain greenwood.edu --primary
  └── After DNS confirmed: python manage.py verify_org_domain --domain greenwood.edu
        └── Sets: is_verified=True, verified_at=now()
        └── Domain now active for auth routing
```

Unverified domains are registered in the DB but silently excluded from auth routing.

---

## 5. Public vs Private Data Split

This is the most important design decision in this app.

```
Public API  (/api/public/<slug>/)          Sys Dashboard API (/sys/org/profile/)
─────────────────────────────────          ──────────────────────────────────────
OrganizationProfile.public_data()          OrganizationProfile (all fields)
                                           OrganizationLegal   (all fields)
```

### Serializer pattern

```python
# PUBLIC serializer — safe for unauthenticated access
class OrgPublicSerializer(serializers.ModelSerializer):
    profile = OrgProfilePublicSerializer(source="profile.public_data")
    domain  = serializers.CharField(source="primary_domain.domain")

    class Meta:
        model = Organization
        fields = ["slug", "profile", "domain"]
        # NOTE: OrganizationLegal is NEVER included here


# SYS DASHBOARD serializer — system_admin only
class OrgLegalSysSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationLegal
        fields = "__all__"
    # Protected by: permission_classes = [IsSystemAdmin]
```

### Profile completion prompts

Both `OrganizationProfile` and `OrganizationLegal` expose a completion percentage property:

```python
org.profile.profile_completion_percent   # 0–100
org.legal.legal_completion_percent       # 0–100
```

Use these in the Sys Dashboard to show a setup checklist on the system admin's first login.

---

## 6. Organization Provisioning Flow

```
Step 1 — Super user creates the org (terminal)
  python manage.py create_org --slug "greenwood-high"
    └── Creates: Organization { slug="greenwood-high", is_active=True }
    └── Creates: OrganizationProfile { org=..., name="" }   ← blank, to be filled
    └── Creates: OrganizationLegal   { org=..., ... }       ← blank, to be filled
    └── Creates: 3 system OrgRoles   (system_admin, admin, member)

Step 2 — Super user registers the domain (terminal)
  python manage.py add_org_domain --org greenwood-high --domain greenwood.edu --primary
    └── Creates: OrgDomain { domain="greenwood.edu", is_primary=True, is_verified=False }

  python manage.py verify_org_domain --domain greenwood.edu
    └── Updates: OrgDomain { is_verified=True, verified_at=now() }

Step 3 — Super user creates the system admin (terminal)
  python manage.py create_system_admin --org greenwood-high --email sysadmin@greenwood.edu
    └── Creates: User + OrgMembership { is_system_admin=True, status=ACTIVE }
    └── Sends: Welcome email with temp password + sys dashboard URL

Step 4 — System admin logs in, completes profile (Sys Dashboard)
  └── Fills in OrganizationProfile (name, logo, address, contact, etc.)
  └── Fills in OrganizationLegal (registration, owner, accreditation)
  └── Dashboard shows completion % until both reach 100%
```

---

## 7. Public Landing Page

Each org's domain serves a public page assembled from `OrganizationProfile`.

### API Endpoint

```
GET https://greenwood.edu/api/public/profile/
  → No auth required
  → Returns OrganizationProfile.public_data()
  → 503 if org.is_active = False
  → 404 if domain is unverified or unknown
```

### What the page shows

```
┌──────────────────────────────────────────────┐
│  [cover_image as hero background]            │
│                                              │
│  [logo]   Greenwood High School              │
│           "Excellence in Education"          │
│           Est. 1995 · Secondary School       │
│                                              │
│  We nurture the leaders of tomorrow...       │
│                                              │
│  📍 123 School Lane, Kathmandu, Nepal        │
│  📞 +977-1-234567                            │
│  ✉️  info@greenwood.edu                      │
│  🌐  greenwood.edu                           │
│                                              │
│  [Facebook] [Instagram] [YouTube]            │
│                                              │
│  ┌──────────────┐  ┌──────────────────────┐  │
│  │  User Login  │  │  Admin Login         │  │
│  └──────────────┘  └──────────────────────┘  │
└──────────────────────────────────────────────┘
```

The two login buttons lead to:
- **User Login** → `/login/` → JWT auth → General Dashboard
- **Admin Login** → `/sys/login/` → Session auth → Sys Dashboard

Both routes pass through domain-based org resolution before credential checking.

---

## 8. File Storage

| File | Model Field | Upload Path | Access |
|---|---|---|---|
| Logo | `OrganizationProfile.logo` | `org_logos/YYYY/` | **Public CDN** |
| Favicon | `OrganizationProfile.favicon` | `org_favicons/YYYY/` | **Public CDN** |
| Cover image | `OrganizationProfile.cover_image` | `org_covers/YYYY/` | **Public CDN** |
| Registration doc | `OrganizationLegal.registration_document` | `private/orgs/<slug>/legal/` | **Private bucket** |
| Accreditation doc | `OrganizationLegal.accreditation_document` | `private/orgs/<slug>/accreditation/` | **Private bucket** |

Public files (logo, favicon, cover) are safe for CDN delivery.
Private files (legal documents) must be served via signed URLs with expiry — never via a public bucket.

---

## 9. Security Considerations

| Risk | Mitigation |
|---|---|
| Cross-org login | Domain-based auth — credentials only valid on their org's domain |
| Legal data exposure | `OrganizationLegal` never included in public serializers |
| Sensitive field leakage | `owner_id_number`, `tax_id_number` — encrypt at rest with `django-fernet-fields` |
| Document access | Private media bucket, signed URL delivery only |
| Unverified domain spoofing | `is_verified=False` domains excluded from all auth routing |
| Org deactivation | `is_active=False` → all logins blocked, public page returns 503 |
| Accreditation expiry | `is_accreditation_expired` property — wire to a Celery alert task |

### Recommended: Encrypt sensitive fields

```python
# Install: pip install django-fernet-fields
from fernet_fields import EncryptedCharField

class OrganizationLegal(TimeStampedModel):
    owner_id_number = EncryptedCharField(max_length=100, blank=True, default="")
    tax_id_number   = EncryptedCharField(max_length=100, blank=True, default="")
```

---

## 10. Future Scaling Notes

### Multi-campus support
Add a `Campus` model with FK to `Organization`. `OrganizationProfile` becomes the org-level profile; campus-level details go on `Campus`.

```
Organization → Campus (FK) → CampusProfile
```

### Org subscription / billing
Add `OrgSubscription` model with plan tier, billing dates, feature entitlements. FK to `Organization`.

### Subdomain routing
If you move to `<slug>.platform.com` subdomains instead of custom domains, the `OrgDomain` model needs no changes — just register `greenwood.platform.com` as the primary domain. The auth middleware already handles it.

---

*Keep this document updated when models change. Legal field additions in particular should be audited for encryption requirements before going to production.*
